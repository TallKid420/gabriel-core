"""Organization management endpoints (tenant-scoped).

    GET    /organizations                              — orgs the caller belongs to
    GET    /organizations/{org_id}                     — organization details
    PATCH  /organizations/{org_id}                     — update display name/metadata
    GET    /organizations/{org_id}/members             — list memberships
    POST   /organizations/{org_id}/members             — add a member (existing user)
    PATCH  /organizations/{org_id}/members/{principal} — change a member's role
    DELETE /organizations/{org_id}/members/{principal} — remove a member

Tenancy: every handler explicitly verifies that the authenticated context
belongs to the addressed organization (defense in depth on top of the PEEL
middleware). Organization *creation* is intentionally not exposed here — new
organizations are created through the public ``POST /auth/register`` flow so
the creator always becomes the owner.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gabriel.api.dependencies import get_db_session_factory, get_execution_context
from gabriel.api.errors import GabrielAPIError
from gabriel.identity.roles import OrgRole, role_at_least
from gabriel.organization.membership_orm import OrgMembershipORM
from gabriel.organization.membership_service import MembershipService
from gabriel.organization.repository import OrganizationRepository
from gabriel.resource.exceptions import DuplicateResourceError, ResourceNotFoundError
from gabriel.runtime.context import ExecutionContext

router = APIRouter(prefix="/organizations", tags=["Organizations"])


class OrganizationUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class AddMemberRequest(BaseModel):
    """Add an existing user (by email) or principal to the organization."""

    email: str | None = None
    principal_id: str | None = None
    role: str = OrgRole.MEMBER.value


class ChangeRoleRequest(BaseModel):
    role: str


def _require_org(context: ExecutionContext, org_id: str) -> None:
    """Tenant isolation: the caller must belong to the addressed org."""
    if context.organization != org_id:
        raise GabrielAPIError(
            "Cross-organization access is forbidden", status_code=403
        )


async def _caller_role(session: AsyncSession, context: ExecutionContext, org_id: str) -> OrgRole | None:
    membership = await MembershipService(session).find_membership(
        org_id, str(context.principal.id)
    )
    return OrgRole(membership.role) if membership else None


def _require_admin(role: OrgRole | None) -> None:
    if role is None or not role_at_least(role, OrgRole.ADMIN):
        raise GabrielAPIError(
            "Organization admin role required", status_code=403
        )


def _membership_view(m: OrgMembershipORM) -> dict[str, Any]:
    return {
        "org_id": m.org_id,
        "principal_id": m.principal_id,
        "user_grn": m.user_grn,
        "role": m.role,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _org_view(orm: Any) -> dict[str, Any]:
    return {
        "grn": orm.grn,
        "org_id": orm.org_id,
        "display_name": orm.display_name,
        "description": orm.description,
        "state": orm.state.value if hasattr(orm.state, "value") else orm.state,
        "version": orm.version,
        "created_at": orm.created_at.isoformat() if orm.created_at else None,
        "updated_at": orm.updated_at.isoformat() if orm.updated_at else None,
    }


@router.get("")
async def list_my_organizations(
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    """List the organizations the calling principal is a member of."""
    async with session_factory() as session:
        memberships = await MembershipService(session).memberships_for_principal(
            str(context.principal.id)
        )
        repo = OrganizationRepository(session)
        items = []
        for membership in memberships:
            org = await repo.get_by_org_id(membership.org_id)
            view = _org_view(org) if org else {"org_id": membership.org_id}
            view["role"] = membership.role
            items.append(view)
    return {"items": items}


@router.get("/{org_id}")
async def get_organization(
    org_id: str,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    _require_org(context, org_id)
    async with session_factory() as session:
        org = await OrganizationRepository(session).get_by_org_id(org_id)
        if org is None:
            raise GabrielAPIError(f"Organization '{org_id}' not found", status_code=404)
        return _org_view(org)


@router.patch("/{org_id}")
async def update_organization(
    org_id: str,
    body: OrganizationUpdateRequest,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    _require_org(context, org_id)
    async with session_factory() as session:
        _require_admin(await _caller_role(session, context, org_id))
        org = await OrganizationRepository(session).get_by_org_id(org_id)
        if org is None:
            raise GabrielAPIError(f"Organization '{org_id}' not found", status_code=404)
        if body.display_name is not None:
            org.display_name = body.display_name
        if body.description is not None:
            org.description = body.description
        org.version += 1
        org.updated_by = str(context.principal.id)
        await session.commit()
        return _org_view(org)


# ── Membership management ────────────────────────────────────────────────────


@router.get("/{org_id}/members")
async def list_members(
    org_id: str,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    _require_org(context, org_id)
    async with session_factory() as session:
        members = await MembershipService(session).list_members(org_id)
        return {"items": [_membership_view(m) for m in members]}


@router.post("/{org_id}/members", status_code=201)
async def add_member(
    org_id: str,
    body: AddMemberRequest,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    """Attach an existing user/principal in this org as a member."""
    _require_org(context, org_id)
    try:
        role = OrgRole(body.role)
    except ValueError as exc:
        raise GabrielAPIError(f"Unknown role '{body.role}'", status_code=422) from exc

    async with session_factory() as session:
        _require_admin(await _caller_role(session, context, org_id))

        principal_id = body.principal_id
        user_grn = None
        if principal_id is None:
            if not body.email:
                raise GabrielAPIError(
                    "Provide 'email' or 'principal_id'", status_code=422
                )
            from gabriel.user.repository import UserRepository

            user = await UserRepository(session).get_by_email(
                body.email.strip().lower(), org_id=org_id
            )
            if user is None:
                raise GabrielAPIError(
                    f"No user with email '{body.email}' in '{org_id}'", status_code=404
                )
            principal_id = user.principal_id
            user_grn = user.grn

        try:
            membership = await MembershipService(session).add_member(
                org_id,
                principal_id,
                role,
                added_by=str(context.principal.id),
                user_grn=user_grn,
                correlation_id=str(context.correlation_id),
            )
        except DuplicateResourceError as exc:
            raise GabrielAPIError(str(exc), status_code=409) from exc
        return _membership_view(membership)


@router.patch("/{org_id}/members/{principal_id:path}")
async def change_member_role(
    org_id: str,
    principal_id: str,
    body: ChangeRoleRequest,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    _require_org(context, org_id)
    try:
        role = OrgRole(body.role)
    except ValueError as exc:
        raise GabrielAPIError(f"Unknown role '{body.role}'", status_code=422) from exc

    async with session_factory() as session:
        _require_admin(await _caller_role(session, context, org_id))
        try:
            membership = await MembershipService(session).change_role(
                org_id,
                principal_id,
                role,
                changed_by=str(context.principal.id),
                correlation_id=str(context.correlation_id),
            )
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        return _membership_view(membership)


@router.delete("/{org_id}/members/{principal_id:path}")
async def remove_member(
    org_id: str,
    principal_id: str,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    _require_org(context, org_id)
    async with session_factory() as session:
        _require_admin(await _caller_role(session, context, org_id))
        service = MembershipService(session)
        try:
            await service.remove_member(
                org_id,
                principal_id,
                removed_by=str(context.principal.id),
                correlation_id=str(context.correlation_id),
            )
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        except ValueError as exc:  # last-owner guard
            raise GabrielAPIError(str(exc), status_code=409) from exc
    return {"removed": True, "principal_id": principal_id}
