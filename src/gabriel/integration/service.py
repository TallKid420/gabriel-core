"""ExternalIntegrationService — business logic for integration credentials."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError

from gabriel.events.event import Event
from gabriel.events.repository import EventRepository
from gabriel.integration.mappers import domain_to_orm, orm_to_domain
from gabriel.integration.models import ExternalIntegration, IntegrationType
from gabriel.integration.repository import ExternalIntegrationRepository
from gabriel.resource.exceptions import DuplicateResourceError, ResourceNotFoundError
from gabriel.resource.grn import GRN
from gabriel.resource.models import ResourceState


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ExternalIntegrationService:
    """Create, read, update, and delete org-scoped integration credentials.

    Callers (tool libraries) use :meth:`get_credentials` to retrieve the
    credentials dict for a given integration type.  The service enforces
    org-scoping — cross-org lookups raise :class:`ResourceNotFoundError`.
    """

    def __init__(
        self,
        repository: ExternalIntegrationRepository,
        event_repo: EventRepository | None = None,
    ) -> None:
        self.repo = repository
        self.event_repo = event_repo

    # ------------------------------------------------------------------
    # Convenience accessor for tool libraries
    # ------------------------------------------------------------------

    async def get_credentials(
        self,
        org_id: str,
        integration_type: IntegrationType,
    ) -> dict[str, Any]:
        """Return the credentials dict for an org + integration type.

        Raises:
            ResourceNotFoundError: If no active integration is configured.
        """
        orm = await self.repo.get_for_org_and_type(org_id, integration_type)
        if orm is None:
            raise ResourceNotFoundError(
                f"No active {integration_type.value} integration for org '{org_id}'. "
                "Configure credentials via ExternalIntegrationService.create()."
            )
        return orm.credentials

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create(
        self,
        org_id: str,
        created_by: str,
        *,
        integration_type: IntegrationType,
        display_name: str,
        credentials: dict[str, Any],
        scopes: str = "",
        integration_grn: str | None = None,
        labels: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> ExternalIntegration:
        grn = (
            GRN.parse(integration_grn)
            if integration_grn
            else GRN.generate(org_id, "integration")
        )
        grn_str = str(grn)

        domain = ExternalIntegration.create(
            grn=grn,
            org_id=org_id,
            created_by=created_by,
            integration_type=integration_type,
            display_name=display_name,
            credentials=credentials,
            scopes=scopes,
            labels=labels or {},
            metadata=metadata or {},
        )

        try:
            persisted_orm = await self.repo.create(domain_to_orm(domain))
            await self._emit(
                "resource_created",
                principal_id=created_by,
                org_id=org_id,
                grn_str=grn_str,
                operation="create",
                correlation_id=correlation_id,
            )
            return orm_to_domain(persisted_orm)
        except IntegrityError as exc:
            raise DuplicateResourceError(
                f"Integration '{grn_str}' already exists."
            ) from exc

    async def get(self, grn_str: str) -> ExternalIntegration:
        return orm_to_domain(await self.repo.get_by_grn(grn_str))

    async def list_for_org(self, org_id: str) -> list[ExternalIntegration]:
        return [orm_to_domain(o) for o in await self.repo.list_for_org(org_id)]

    async def update_credentials(
        self,
        grn_str: str,
        updated_by: str,
        *,
        credentials: dict[str, Any],
        scopes: str | None = None,
        is_active: bool | None = None,
        correlation_id: str | None = None,
    ) -> ExternalIntegration:
        existing = orm_to_domain(await self.repo.get_by_grn(grn_str))
        updated = existing.model_copy(
            update={
                "credentials": credentials,
                "scopes": scopes if scopes is not None else existing.scopes,
                "is_active": is_active if is_active is not None else existing.is_active,
                "updated_by": updated_by,
                "updated_at": _utcnow(),
                "version": existing.version + 1,
                "state": ResourceState.ACTIVE,
            }
        )
        persisted = await self.repo.update(domain_to_orm(updated))
        await self._emit(
            "resource_updated",
            principal_id=updated_by,
            org_id=existing.org_id,
            grn_str=grn_str,
            operation="update_credentials",
            correlation_id=correlation_id,
        )
        return orm_to_domain(persisted)

    async def delete(
        self,
        grn_str: str,
        deleted_by: str,
        *,
        correlation_id: str | None = None,
    ) -> None:
        existing = orm_to_domain(await self.repo.get_by_grn(grn_str))
        await self.repo.delete(grn_str)
        await self._emit(
            "resource_deleted",
            principal_id=deleted_by,
            org_id=existing.org_id,
            grn_str=grn_str,
            operation="delete",
            correlation_id=correlation_id,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _emit(
        self,
        event_type: str,
        *,
        principal_id: str,
        org_id: str,
        grn_str: str,
        operation: str,
        correlation_id: str | None,
    ) -> None:
        if self.event_repo is None:
            return
        await self.event_repo.append(
            Event(
                type=event_type,
                principal_id=principal_id,
                organization_id=org_id,
                resource_grn=grn_str,
                correlation_id=correlation_id,
                payload={"resource_type": "integration", "grn": grn_str},
                metadata={
                    "service": "ExternalIntegrationService",
                    "operation": operation,
                },
            )
        )
