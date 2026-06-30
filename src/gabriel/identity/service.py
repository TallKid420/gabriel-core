"""Principal lifecycle service.

Integrates ADR-009 (GRN Factory Integration): Principal creation is routed
through ResourceFactory to ensure uniform identifier minting and defaults.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from gabriel.events.event import Event
from gabriel.identity.exceptions import PrincipalNotFoundError
from gabriel.identity.models import Capability, PrincipalStatus, PrincipalType
from gabriel.identity.principal import Principal
from gabriel.identity.principal_id import PrincipalID
from gabriel.resource.grn import GRN
from gabriel.resource.factory import ResourceFactory
from gabriel.resource.registry import ResourceRegistry, registry
from gabriel.resource.bootstrap import register_core_resource_types


class PrincipalRepositoryProtocol(Protocol):
    async def create(self, principal: Principal) -> Principal: ...

    async def get_by_id(self, principal_id: str) -> Principal | None: ...

    async def list_for_org(self, org_id: str) -> list[Principal]: ...


class EventRepositoryProtocol(Protocol):
    async def append(self, event: Event) -> Any: ...


class PrincipalService:
    """Business logic for principals.

    Principals remain identity primitives keyed by PrincipalID. Each principal
    is mirrored by a GRN-addressable resource, so the service stores the link
    on the principal record and can emit a creation event for audit trails.
    
    Creation is routed through ResourceFactory (ADR-009) to ensure uniform
    identifier minting and default handling.
    """

    def __init__(
        self,
        repository: PrincipalRepositoryProtocol,
        registry_instance: ResourceRegistry | None = None,
        event_repo: EventRepositoryProtocol | None = None,
    ) -> None:
        # Bootstrap (idempotent, safe to call multiple times)
        register_core_resource_types()
        
        self.repo = repository
        self.event_repo = event_repo
        self.registry = registry_instance or registry
        self.factory = ResourceFactory(self.registry)

    async def register_principal(
        self,
        org_id: str,
        principal_type: PrincipalType | str,
        principal_identifier: str,
        display_name: str,
        capabilities: Iterable[Capability | str] = (),
        created_by: str | None = None,
        *,
        resource_grn: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Principal:
        """Create, persist, and optionally audit a new principal.

        Creation is routed through ResourceFactory to ensure uniform identifier
        minting and defaults (ADR-009).

        Args:
            org_id: Owning organization.
            principal_type: Principal kind, usually a `PrincipalType` value.
            principal_identifier: Unique identifier within org (e.g., 'alice', 'bot-01').
            display_name: Human-readable name.
            capabilities: Capability enum values or string values.
            created_by: Principal ID string of the creator (defaults to system).
            resource_grn: Optional mirrored resource GRN. If omitted, one is minted.
            metadata: Optional extra metadata.

        Returns:
            The persisted principal domain object.
        """
        created_by = created_by or "system"
        
        normalized_type = self._normalize_principal_type(principal_type)
        principal_id = PrincipalID(
            org_id=org_id,
            principal_type=normalized_type.value,
            principal_identifier=principal_identifier,
        )

        mirrored_resource_grn = resource_grn or str(
            GRN.generate(org_id=org_id, resource_type=normalized_type.value)
        )

        # Create through factory (uniform path, ADR-009)
        principal = self.factory.create(
            "principal",
            id=principal_id,
            resource_grn=mirrored_resource_grn,
            organization_id=org_id,
            principal_type=normalized_type,
            display_name=display_name,
            status=PrincipalStatus.ACTIVE,
            capabilities=self._normalize_capabilities(capabilities),
            metadata={
                "created_by": created_by,
                **(metadata or {}),
            },
        )

        persisted = await self.repo.create(principal)
        await self._emit_principal_created(persisted, created_by)
        # Commit event transaction if event_repo is provided
        if self.event_repo is not None:
            await self.repo.session.commit()
        return persisted

    async def get_principal(self, principal_id: str) -> Principal:
        """Fetch a principal by its PrincipalID string."""
        principal = await self.repo.get_by_id(principal_id)
        if principal is None:
            raise PrincipalNotFoundError(f"Principal '{principal_id}' was not found")
        return principal

    async def list_principals_for_org(self, org_id: str) -> list[Principal]:
        """List all principals scoped to an organization."""
        return await self.repo.list_for_org(org_id)

    async def _emit_principal_created(self, principal: Principal, created_by: str) -> None:
        if self.event_repo is None:
            return

        event = Event(
            type="resource_created",
            principal_id=created_by,
            organization_id=principal.organization_id,
            resource_grn=principal.resource_grn,
            payload={
                "resource_type": "principal",
                "principal_id": str(principal.id),
                "principal_type": principal.principal_type.value,
                "display_name": principal.display_name,
                "resource_grn": principal.resource_grn,
            },
        )

        append = getattr(self.event_repo, "append", None)
        if callable(append):
            await append(event)

    @staticmethod
    def _normalize_principal_type(principal_type: PrincipalType | str) -> PrincipalType:
        if isinstance(principal_type, PrincipalType):
            return principal_type
        return PrincipalType(principal_type)

    @staticmethod
    def _normalize_capabilities(
        capabilities: Iterable[Capability | str],
    ) -> set[Capability]:
        normalized: set[Capability] = set()
        for capability in capabilities:
            normalized.add(capability if isinstance(capability, Capability) else Capability(capability))
        return normalized

    @staticmethod
    def _slugify(value: str) -> str:
        return "-".join(value.strip().lower().split())
