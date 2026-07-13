"""Self-service registration: organization + owner user in one transaction.

``POST /auth/register`` is the public entry point to the platform. A new
signup creates:

* an :class:`~gabriel.organization.models.Organization` (either the requested
  ``organization_name`` or a personal org derived from the email),
* the first :class:`~gabriel.user.models.User` with the ``owner`` role,
* the mirrored :class:`~gabriel.identity.principal.Principal` and org
  membership,
* ``resource_created`` domain events for both resources,

all committed atomically (ADR-017 transactional outbox). If anything fails,
nothing is persisted — no orphan organizations.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gabriel.events.event import Event
from gabriel.events.repository import EventRepository
from gabriel.identity.roles import OrgRole
from gabriel.organization.mappers import domain_to_orm as org_domain_to_orm
from gabriel.organization.models import Organization
from gabriel.organization.repository import OrganizationRepository
from gabriel.resource.bootstrap import register_core_resource_types
from gabriel.resource.exceptions import DuplicateResourceError
from gabriel.resource.factory import ResourceFactory
from gabriel.resource.grn import GRN
from gabriel.resource.models import ResourceState
from gabriel.resource.registry import registry
from gabriel.user.models import User
from gabriel.user.service import UserService


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "org"


@dataclass(frozen=True)
class RegistrationResult:
    """Outcome of a successful signup."""

    user: User
    organization: Organization


class RegistrationService:
    """Creates a new organization together with its first (owner) user."""

    def __init__(self, session: AsyncSession) -> None:
        register_core_resource_types()
        self.session = session
        self.org_repo = OrganizationRepository(session)
        self.event_repo = EventRepository(session)
        self.user_service = UserService(session, self.event_repo)
        self.factory = ResourceFactory(registry)

    async def register(
        self,
        email: str,
        password: str,
        display_name: str,
        organization_name: str | None = None,
        *,
        correlation_id: str | None = None,
    ) -> RegistrationResult:
        """Register a new organization and its owner user, atomically.

        Args:
            email: Owner's email (unique within the new organization).
            password: Owner's password (plaintext; hashed before storage).
            display_name: Owner's display name.
            organization_name: Organization display name. When omitted, a
                personal organization is derived from the email local part.
            correlation_id: Optional trace id propagated to emitted events.

        Raises:
            DuplicateResourceError: If the derived org_id is already taken.
        """
        email = email.strip().lower()
        org_display = (organization_name or "").strip() or f"{email.split('@', 1)[0]}'s workspace"
        org_id = await self._unique_org_id(_slugify(org_display), allow_suffix=organization_name is None)

        # 1. Build + stage the organization (no commit yet)
        org_grn = GRN.generate(org_id, "organization")
        organization: Organization = self.factory.create(
            "organization",
            grn=org_grn,
            org_id=org_id,
            display_name=org_display,
            state=ResourceState.ACTIVE,
            created_by=email,
            updated_by=email,
        )
        self.session.add(org_domain_to_orm(organization))
        await self.event_repo.append(
            Event(
                type="resource_created",
                principal_id=email,
                organization_id=org_id,
                resource_grn=str(org_grn),
                correlation_id=correlation_id,
                payload={
                    "resource_type": "organization",
                    "org_id": org_id,
                    "display_name": org_display,
                    "grn": str(org_grn),
                },
                metadata={
                    "service": "RegistrationService",
                    "operation": "register",
                },
            )
        )

        # 2. Owner user + principal + membership + events, then ONE commit.
        try:
            user = await self.user_service.register_user(
                org_id=org_id,
                email=email,
                password=password,
                display_name=display_name,
                role=OrgRole.OWNER,
                created_by=email,
                correlation_id=correlation_id,
                commit=True,
            )
        except IntegrityError as exc:  # pragma: no cover - defensive
            await self.session.rollback()
            raise DuplicateResourceError(
                f"Registration for '{email}' conflicts with existing records"
            ) from exc

        return RegistrationResult(user=user, organization=organization)

    async def _unique_org_id(self, base_slug: str, *, allow_suffix: bool) -> str:
        """Ensure the org_id is free; personal orgs get a numeric suffix."""
        if await self.org_repo.get_by_org_id(base_slug) is None:
            return base_slug
        if not allow_suffix:
            raise DuplicateResourceError(
                f"Organization with org_id '{base_slug}' already exists."
            )
        for i in range(2, 100):
            candidate = f"{base_slug}-{i}"
            if await self.org_repo.get_by_org_id(candidate) is None:
                return candidate
        raise DuplicateResourceError(
            f"Could not derive a unique organization id from '{base_slug}'"
        )
