"""User lifecycle service.

Registers and manages User resources and their mirrored Principals.
Everything happens in ONE database transaction (ADR-017 transactional outbox):

    user row + principal row + membership row + domain events → single commit

Design notes
------------
* Creation goes through :class:`ResourceFactory` (ADR-009: uniform GRN minting).
* The password hash never leaves this module in API responses.
* Capabilities on the mirrored principal are derived from the org role
  (see ``gabriel.identity.roles``) — the identity-based PEEL layer.
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gabriel.events.event import Event
from gabriel.events.repository import EventRepository
from gabriel.identity.exceptions import AuthenticationFailedError
from gabriel.identity.mappers import domain_to_orm as principal_domain_to_orm
from gabriel.identity.models import PrincipalStatus, PrincipalType
from gabriel.identity.passwords import hash_password, verify_password
from gabriel.identity.principal import Principal
from gabriel.identity.principal_id import PrincipalID
from gabriel.identity.roles import OrgRole, capabilities_for_role
from gabriel.organization.membership_service import MembershipService
from gabriel.resource.bootstrap import register_core_resource_types
from gabriel.resource.exceptions import DuplicateResourceError
from gabriel.resource.factory import ResourceFactory
from gabriel.resource.grn import GRN
from gabriel.resource.models import ResourceState
from gabriel.resource.registry import registry
from gabriel.user.mappers import domain_to_orm, orm_to_domain
from gabriel.user.models import User
from gabriel.user.repository import UserRepository


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "user"


class UserService:
    """Business logic for user accounts (org-scoped)."""

    def __init__(self, session: AsyncSession, event_repo: EventRepository | None = None):
        register_core_resource_types()
        self.session = session
        self.repo = UserRepository(session)
        self.event_repo = event_repo or EventRepository(session)
        self.membership = MembershipService(session, self.event_repo)
        self.factory = ResourceFactory(registry)

    # ── Registration ─────────────────────────────────────────────────────────

    async def register_user(
        self,
        org_id: str,
        email: str,
        password: str,
        display_name: str,
        *,
        role: OrgRole | str = OrgRole.MEMBER,
        created_by: str = "system",
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        commit: bool = True,
    ) -> User:
        """Create a user + mirrored principal + org membership, atomically.

        Raises:
            DuplicateResourceError: If the email is already used in this org.
        """
        email = email.strip().lower()
        normalized_role = role if isinstance(role, OrgRole) else OrgRole(role)

        if await self.repo.get_by_email(email, org_id=org_id) is not None:
            raise DuplicateResourceError(
                f"A user with email '{email}' already exists in organization '{org_id}'"
            )

        # 1. Mint identifiers (uniform path, ADR-009)
        user_grn = GRN.generate(org_id=org_id, resource_type="user")
        principal_id = PrincipalID(
            org_id=org_id,
            principal_type=PrincipalType.USER.value,
            principal_identifier=f"{_slugify(email.split('@', 1)[0])}-{user_grn.resource_id[:8]}",
        )

        # 2. Build the mirrored Principal with role-derived capabilities
        principal = self.factory.create(
            "principal",
            id=principal_id,
            resource_grn=str(user_grn),
            organization_id=org_id,
            principal_type=PrincipalType.USER,
            display_name=display_name,
            status=PrincipalStatus.ACTIVE,
            capabilities=capabilities_for_role(normalized_role),
            metadata={
                "email": email,
                "roles": [normalized_role.value],
                "created_by": created_by,
            },
        )

        # 3. Build the User resource
        user: User = self.factory.create(
            "user",
            grn=user_grn,
            org_id=org_id,
            state=ResourceState.ACTIVE,
            created_by=created_by,
            updated_by=created_by,
            email=email,
            display_name=display_name,
            principal_id=str(principal_id),
            password_hash=hash_password(password),
            metadata=metadata or {},
        )

        # 4. Persist user + principal + membership + events in ONE transaction
        try:
            user_orm = await self.repo.create(domain_to_orm(user))
            self.session.add(principal_domain_to_orm(principal))
            await self.membership.add_member(
                org_id,
                str(principal_id),
                normalized_role,
                added_by=created_by,
                user_grn=str(user_grn),
                correlation_id=correlation_id,
                commit=False,
            )
            await self.event_repo.append(
                Event(
                    type="resource_created",
                    principal_id=created_by,
                    organization_id=org_id,
                    resource_grn=str(user_grn),
                    correlation_id=correlation_id,
                    payload={
                        "resource_type": "user",
                        "grn": str(user_grn),
                        "email": email,
                        "display_name": display_name,
                        "principal_id": str(principal_id),
                        "role": normalized_role.value,
                    },
                    metadata={"service": "UserService", "operation": "register_user"},
                )
            )
            if commit:
                await self.session.commit()
            else:
                await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise DuplicateResourceError(
                f"User '{email}' conflicts with an existing record in '{org_id}'"
            ) from exc

        return orm_to_domain(user_orm)

    # ── Authentication support ───────────────────────────────────────────────

    async def authenticate(
        self, email: str, password: str, org_id: str | None = None
    ) -> User:
        """Verify email + password and return the user (for the password provider).

        Raises:
            AuthenticationFailedError: On unknown email, wrong password, or
                inactive account. The error message is deliberately uniform to
                avoid user enumeration.
        """
        failure = AuthenticationFailedError("Invalid email or password")
        try:
            user_orm = await self.repo.get_by_email(email.strip().lower(), org_id=org_id)
        except ValueError as exc:  # ambiguous email across orgs
            raise AuthenticationFailedError(str(exc)) from exc
        if user_orm is None or not user_orm.password_hash:
            raise failure
        if not verify_password(password, user_orm.password_hash):
            raise failure
        if user_orm.state != ResourceState.ACTIVE:
            raise AuthenticationFailedError("Account is not active")
        return orm_to_domain(user_orm)

    async def change_password(
        self,
        grn_str: str,
        current_password: str,
        new_password: str,
        *,
        changed_by: str,
        correlation_id: str | None = None,
    ) -> None:
        """Rotate a user's password after verifying the current one."""
        user_orm = await self.repo.get_by_grn(grn_str)
        if not user_orm.password_hash or not verify_password(
            current_password, user_orm.password_hash
        ):
            raise AuthenticationFailedError("Current password is incorrect")
        user_orm.password_hash = hash_password(new_password)
        user_orm.version += 1
        user_orm.updated_by = changed_by
        await self.event_repo.append(
            Event(
                type="user_password_changed",
                principal_id=changed_by,
                organization_id=user_orm.org_id,
                resource_grn=grn_str,
                correlation_id=correlation_id,
                payload={"grn": grn_str},
                metadata={"service": "UserService"},
            )
        )
        await self.session.commit()

    # ── CRUD ─────────────────────────────────────────────────────────────────

    async def get_user(self, grn_str: str) -> User:
        return orm_to_domain(await self.repo.get_by_grn(grn_str))

    async def get_user_by_principal(self, principal_id: str) -> User | None:
        orm = await self.repo.get_by_principal_id(principal_id)
        return orm_to_domain(orm) if orm else None

    async def list_users_for_org(self, org_id: str) -> list[User]:
        return [orm_to_domain(orm) for orm in await self.repo.list_for_org(org_id)]

    async def update_user(
        self,
        grn_str: str,
        *,
        updated_by: str,
        display_name: str | None = None,
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> User:
        """Update mutable profile fields; bumps the resource version."""
        user_orm = await self.repo.get_by_grn(grn_str)
        if display_name is not None:
            user_orm.display_name = display_name
        if metadata is not None:
            user_orm.resource_metadata = {**user_orm.resource_metadata, **metadata}
        user_orm.version += 1
        user_orm.updated_by = updated_by
        await self.event_repo.append(
            Event(
                type="resource_updated",
                principal_id=updated_by,
                organization_id=user_orm.org_id,
                resource_grn=grn_str,
                correlation_id=correlation_id,
                payload={
                    "resource_type": "user",
                    "grn": grn_str,
                    "display_name": user_orm.display_name,
                },
                metadata={"service": "UserService", "operation": "update_user"},
            )
        )
        await self.session.commit()
        return orm_to_domain(user_orm)

    async def deactivate_user(
        self,
        grn_str: str,
        *,
        deactivated_by: str,
        correlation_id: str | None = None,
    ) -> User:
        """Soft-delete: mark the user resource DELETED (audit trail preserved)."""
        user_orm = await self.repo.get_by_grn(grn_str)
        user_orm.state = ResourceState.DELETED
        user_orm.version += 1
        user_orm.updated_by = deactivated_by
        await self.event_repo.append(
            Event(
                type="resource_deleted",
                principal_id=deactivated_by,
                organization_id=user_orm.org_id,
                resource_grn=grn_str,
                correlation_id=correlation_id,
                payload={"resource_type": "user", "grn": grn_str},
                metadata={"service": "UserService", "operation": "deactivate_user"},
            )
        )
        await self.session.commit()
        return orm_to_domain(user_orm)
