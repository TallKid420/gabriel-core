"""Membership service: manage a principal's seat and role within an org.

Emits domain events for every membership state change (P-4: event-driven;
ADR-017 transactional outbox — events are appended in the same session as the
membership row and committed together by the caller/service).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gabriel.events.event import Event
from gabriel.events.repository import EventRepository
from gabriel.identity.roles import OrgRole
from gabriel.organization.membership_orm import OrgMembershipORM
from gabriel.resource.exceptions import DuplicateResourceError, ResourceNotFoundError


class MembershipService:
    """Business logic for organization memberships (org-scoped by design)."""

    def __init__(self, session: AsyncSession, event_repo: EventRepository | None = None):
        self.session = session
        self.event_repo = event_repo

    async def add_member(
        self,
        org_id: str,
        principal_id: str,
        role: OrgRole | str,
        added_by: str,
        *,
        user_grn: str | None = None,
        correlation_id: str | None = None,
        commit: bool = True,
    ) -> OrgMembershipORM:
        """Add ``principal_id`` to ``org_id`` with ``role``."""
        normalized_role = role if isinstance(role, OrgRole) else OrgRole(role)

        existing = await self._get(org_id, principal_id)
        if existing is not None:
            raise DuplicateResourceError(
                f"Principal '{principal_id}' is already a member of '{org_id}'"
            )

        membership = OrgMembershipORM(
            org_id=org_id,
            principal_id=principal_id,
            user_grn=user_grn,
            role=normalized_role.value,
            created_by=added_by,
        )
        self.session.add(membership)
        await self._emit(
            "org_member_added",
            org_id=org_id,
            acting_principal=added_by,
            resource_grn=user_grn,
            correlation_id=correlation_id,
            payload={
                "principal_id": principal_id,
                "role": normalized_role.value,
            },
        )
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
        return membership

    async def change_role(
        self,
        org_id: str,
        principal_id: str,
        new_role: OrgRole | str,
        changed_by: str,
        *,
        correlation_id: str | None = None,
        commit: bool = True,
    ) -> OrgMembershipORM:
        """Change a member's role."""
        normalized_role = new_role if isinstance(new_role, OrgRole) else OrgRole(new_role)
        membership = await self._get_or_raise(org_id, principal_id)

        old_role = membership.role
        membership.role = normalized_role.value
        await self._emit(
            "org_member_role_changed",
            org_id=org_id,
            acting_principal=changed_by,
            resource_grn=membership.user_grn,
            correlation_id=correlation_id,
            payload={
                "principal_id": principal_id,
                "old_role": old_role,
                "new_role": normalized_role.value,
            },
        )
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
        return membership

    async def remove_member(
        self,
        org_id: str,
        principal_id: str,
        removed_by: str,
        *,
        correlation_id: str | None = None,
        commit: bool = True,
    ) -> None:
        """Remove a member from the organization."""
        membership = await self._get_or_raise(org_id, principal_id)

        # Safety: an organization must always retain at least one owner.
        if membership.role == OrgRole.OWNER.value:
            owners = [
                m for m in await self.list_members(org_id)
                if m.role == OrgRole.OWNER.value
            ]
            if len(owners) <= 1:
                raise ValueError(
                    f"Cannot remove the last owner of organization '{org_id}'"
                )

        await self.session.delete(membership)
        await self._emit(
            "org_member_removed",
            org_id=org_id,
            acting_principal=removed_by,
            resource_grn=membership.user_grn,
            correlation_id=correlation_id,
            payload={"principal_id": principal_id, "role": membership.role},
        )
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()

    async def list_members(self, org_id: str) -> list[OrgMembershipORM]:
        """List all memberships for an organization (org-scoped)."""
        result = await self.session.execute(
            select(OrgMembershipORM)
            .filter_by(org_id=org_id)
            .order_by(OrgMembershipORM.created_at)
        )
        return list(result.scalars().all())

    async def get_membership(
        self, org_id: str, principal_id: str
    ) -> OrgMembershipORM:
        return await self._get_or_raise(org_id, principal_id)

    async def find_membership(
        self, org_id: str, principal_id: str
    ) -> OrgMembershipORM | None:
        """Like :meth:`get_membership` but returns ``None`` when absent."""
        return await self._get(org_id, principal_id)

    async def memberships_for_principal(
        self, principal_id: str
    ) -> list[OrgMembershipORM]:
        result = await self.session.execute(
            select(OrgMembershipORM).filter_by(principal_id=principal_id)
        )
        return list(result.scalars().all())

    # ── internal ────────────────────────────────────────────────────────────

    async def _get(self, org_id: str, principal_id: str) -> OrgMembershipORM | None:
        result = await self.session.execute(
            select(OrgMembershipORM).filter_by(
                org_id=org_id, principal_id=principal_id
            )
        )
        return result.scalar_one_or_none()

    async def _get_or_raise(self, org_id: str, principal_id: str) -> OrgMembershipORM:
        membership = await self._get(org_id, principal_id)
        if membership is None:
            raise ResourceNotFoundError(
                f"Principal '{principal_id}' is not a member of '{org_id}'"
            )
        return membership

    async def _emit(
        self,
        event_type: str,
        *,
        org_id: str,
        acting_principal: str,
        resource_grn: str | None,
        correlation_id: str | None,
        payload: dict,
    ) -> None:
        if self.event_repo is None:
            return
        await self.event_repo.append(
            Event(
                type=event_type,
                principal_id=acting_principal,
                organization_id=org_id,
                resource_grn=resource_grn,
                correlation_id=correlation_id,
                payload=payload,
                metadata={"service": "MembershipService"},
            )
        )
