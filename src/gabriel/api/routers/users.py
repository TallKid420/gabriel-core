"""User management endpoints (org-scoped).

    GET    /users                — list users in the caller's organization
    POST   /users                — create a user (admin invites a teammate)
    GET    /users/me             — the caller's own user record
    POST   /users/me/password    — change own password
    GET    /users/{grn}          — fetch a user by GRN
    PATCH  /users/{grn}          — update profile fields
    DELETE /users/{grn}          — deactivate (soft delete)

All routes operate strictly within the authenticated organization: GRNs from
other organizations are rejected (tenant isolation, defense in depth on top of
the PEEL middleware; capability enforcement comes from ``user:*`` actions in
``gabriel.policy.capabilities``).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gabriel.api.dependencies import get_db_session_factory, get_execution_context
from gabriel.api.errors import GabrielAPIError
from gabriel.api.tenancy import require_same_org
from gabriel.identity.exceptions import AuthenticationFailedError
from gabriel.identity.roles import OrgRole
from gabriel.resource.exceptions import DuplicateResourceError, ResourceNotFoundError
from gabriel.resource.grn import GRN
from gabriel.runtime.context import ExecutionContext
from gabriel.user.service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


class UserCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=256)
    display_name: str = Field(min_length=1, max_length=200)
    role: str = OrgRole.MEMBER.value


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    metadata: dict | None = None


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=256)


@router.get("")
async def list_users(
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    async with session_factory() as session:
        users = await UserService(session).list_users_for_org(context.organization)
        return {"items": [user.public_view() for user in users]}


@router.post("", status_code=201)
async def create_user(
    body: UserCreateRequest,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    """Create a teammate in the caller's organization (admin action)."""
    try:
        role = OrgRole(body.role)
    except ValueError as exc:
        raise GabrielAPIError(f"Unknown role '{body.role}'", status_code=422) from exc

    async with session_factory() as session:
        try:
            user = await UserService(session).register_user(
                org_id=context.organization,
                email=body.email,
                password=body.password,
                display_name=body.display_name,
                role=role,
                created_by=str(context.principal.id),
                correlation_id=str(context.correlation_id),
            )
        except DuplicateResourceError as exc:
            raise GabrielAPIError(str(exc), status_code=409) from exc
        return user.public_view()


@router.get("/me")
async def get_own_user(
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    async with session_factory() as session:
        user = await UserService(session).get_user_by_principal(
            str(context.principal.id)
        )
        if user is None:
            raise GabrielAPIError(
                "No user record for the calling principal", status_code=404
            )
        return user.public_view()


@router.post("/me/password")
async def change_own_password(
    body: PasswordChangeRequest,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    async with session_factory() as session:
        service = UserService(session)
        user = await service.get_user_by_principal(str(context.principal.id))
        if user is None:
            raise GabrielAPIError(
                "No user record for the calling principal", status_code=404
            )
        try:
            await service.change_password(
                str(user.grn),
                body.current_password,
                body.new_password,
                changed_by=str(context.principal.id),
                correlation_id=str(context.correlation_id),
            )
        except AuthenticationFailedError as exc:
            raise GabrielAPIError(str(exc), status_code=403) from exc
    return {"ok": True}


@router.get("/{grn:path}")
async def get_user(
    grn: str,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    require_same_org(context, grn)
    async with session_factory() as session:
        try:
            user = await UserService(session).get_user(grn)
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        return user.public_view()


@router.patch("/{grn:path}")
async def update_user(
    grn: str,
    body: UserUpdateRequest,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    require_same_org(context, grn)
    async with session_factory() as session:
        try:
            user = await UserService(session).update_user(
                grn,
                updated_by=str(context.principal.id),
                display_name=body.display_name,
                metadata=body.metadata,
                correlation_id=str(context.correlation_id),
            )
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        return user.public_view()


@router.delete("/{grn:path}")
async def deactivate_user(
    grn: str,
    context: ExecutionContext = Depends(get_execution_context),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    require_same_org(context, grn)
    async with session_factory() as session:
        try:
            user = await UserService(session).deactivate_user(
                grn,
                deactivated_by=str(context.principal.id),
                correlation_id=str(context.correlation_id),
            )
        except ResourceNotFoundError as exc:
            raise GabrielAPIError(str(exc), status_code=404) from exc
        return user.public_view()
