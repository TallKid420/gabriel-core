"""Authentication endpoints.

    POST /auth/register — self-service signup: organization + owner user
    POST /auth/login    — authenticate via a provider, issue a signed token
    POST /auth/refresh  — rotate a refresh token, mint a new access token
    POST /auth/logout   — revoke the refresh token, clear the session cookie
    GET  /auth/me       — current authenticated principal
    GET  /auth/jwks     — public keys for verifying issued tokens

Backwards-compatible development aliases (``/auth/dev/login``,
``/auth/dev/principals``, ``/auth/session``) are preserved for the existing
frontend and are only functional while the dev provider is enabled.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gabriel.api.auth import authenticate_token, extract_bearer_token
from gabriel.api.errors import AuthenticationError, GabrielAPIError
from gabriel.api.dependencies import get_db_session_factory, get_identity_service
from gabriel.identity.exceptions import (
    AuthenticationFailedError,
    ProviderNotFoundError,
)
from gabriel.identity.identity_service import IdentityService
from gabriel.identity.refresh import RefreshTokenService
from gabriel.identity.registration import RegistrationService
from gabriel.identity.repository import PrincipalRepository
from gabriel.resource.exceptions import DuplicateResourceError

router = APIRouter(prefix="/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    """Login payload: a provider ``method`` plus method-specific credentials."""

    method: str = "dev"
    credentials: dict[str, Any] = Field(default_factory=dict)
    # Convenience: allow ``{"userId": "..."}`` at the top level for dev login.
    userId: str | None = None


class RegisterRequest(BaseModel):
    """Signup payload: creates an organization and its owner user."""

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=256)
    display_name: str = Field(min_length=1, max_length=200)
    organization_name: str | None = Field(default=None, max_length=200)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        local, sep, domain = value.partition("@")
        if not sep or not local or "." not in domain or domain.startswith("."):
            raise ValueError("Invalid email address")
        return value


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


def _set_session_cookie(
    response: Response, identity_service: IdentityService, token_value: str, max_age: int
) -> None:
    response.set_cookie(
        key=identity_service.settings.session_cookie_name,
        value=token_value,
        httponly=True,
        secure=identity_service.settings.session_cookie_secure,
        samesite="lax",
        max_age=max_age,
    )


@router.post("/register", status_code=201)
async def register(
    body: RegisterRequest,
    response: Response,
    identity_service: IdentityService = Depends(get_identity_service),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    """Self-service signup: create an organization and its owner user, then log in."""
    async with session_factory() as session:
        try:
            registration = await RegistrationService(session).register(
                email=body.email,
                password=body.password,
                display_name=body.display_name,
                organization_name=body.organization_name,
            )
        except DuplicateResourceError as exc:
            raise GabrielAPIError(str(exc), status_code=409) from exc

    # Log the new owner in through the standard provider path.
    try:
        result = await identity_service.login(
            "password",
            {
                "email": body.email,
                "password": body.password,
                "org_id": registration.organization.org_id,
            },
        )
    except (ProviderNotFoundError, AuthenticationFailedError) as exc:
        raise GabrielAPIError(
            "Registration succeeded but automatic login failed", status_code=500
        ) from exc

    async with session_factory() as session:
        refresh_token = await RefreshTokenService(session).issue(
            str(result.principal.id), result.principal.organization_id
        )

    _set_session_cookie(
        response,
        identity_service,
        result.token.value,
        identity_service.settings.token_ttl_seconds,
    )
    return {
        "access_token": result.token.value,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_at": result.token.expires_at.isoformat(),
        "session": result.session,
        "user": registration.user.public_view(),
        "organization": {
            "id": registration.organization.org_id,
            "name": registration.organization.display_name,
            "grn": str(registration.organization.grn),
        },
    }


@router.post("/login")
async def login(
    body: LoginRequest,
    response: Response,
    identity_service: IdentityService = Depends(get_identity_service),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    """Authenticate and issue a signed session token."""
    credentials = dict(body.credentials)
    if body.userId and "userId" not in credentials:
        credentials["userId"] = body.userId

    try:
        result = await identity_service.login(body.method, credentials)
    except ProviderNotFoundError as exc:
        raise GabrielAPIError(str(exc), status_code=400) from exc
    except AuthenticationFailedError as exc:
        raise AuthenticationError(str(exc)) from exc

    _set_session_cookie(
        response,
        identity_service,
        result.token.value,
        identity_service.settings.token_ttl_seconds,
    )

    payload = {
        "access_token": result.token.value,
        "token_type": "bearer",
        "expires_at": result.token.expires_at.isoformat(),
        "session": result.session,
    }

    # Refresh tokens are only meaningful for DB-backed principals.
    if body.method == "password":
        async with session_factory() as session:
            payload["refresh_token"] = await RefreshTokenService(session).issue(
                str(result.principal.id), result.principal.organization_id
            )

    return payload


@router.post("/refresh")
async def refresh(
    body: RefreshRequest,
    response: Response,
    identity_service: IdentityService = Depends(get_identity_service),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    """Rotate a refresh token and mint a fresh access token (single-use rotation)."""
    async with session_factory() as session:
        try:
            new_refresh, principal_id, _org_id = await RefreshTokenService(
                session
            ).rotate(body.refresh_token)
        except AuthenticationFailedError as exc:
            raise AuthenticationError(str(exc)) from exc

        principal = await PrincipalRepository(session).get_by_id(principal_id)

    if principal is None:
        raise AuthenticationError("Principal for refresh token no longer exists")

    token = identity_service.token_service.issue(principal)
    _set_session_cookie(
        response,
        identity_service,
        token.value,
        identity_service.settings.token_ttl_seconds,
    )
    return {
        "access_token": token.value,
        "refresh_token": new_refresh,
        "token_type": "bearer",
        "expires_at": token.expires_at.isoformat(),
    }


@router.post("/logout")
async def logout(
    response: Response,
    body: LogoutRequest | None = None,
    identity_service: IdentityService = Depends(get_identity_service),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
):
    """Invalidate the session: revoke the refresh token, clear the cookie."""
    if body is not None and body.refresh_token:
        async with session_factory() as session:
            await RefreshTokenService(session).revoke(body.refresh_token)
    response.delete_cookie(identity_service.settings.session_cookie_name)
    return {"ok": True}


@router.get("/me")
async def me(
    request: Request,
    identity_service: IdentityService = Depends(get_identity_service),
):
    """Return the currently authenticated principal."""
    token = extract_bearer_token(request.headers.get("authorization"))
    if token is None:
        token = request.cookies.get(identity_service.settings.session_cookie_name)

    auth = await authenticate_token(identity_service, token)
    principal = auth.principal
    return {
        "principal_id": str(principal.id),
        "organization_id": principal.organization_id,
        "principal_type": principal.principal_type.value,
        "display_name": principal.display_name,
        "capabilities": sorted(cap.value for cap in principal.capabilities),
        "metadata": principal.metadata,
    }


@router.get("/jwks")
async def jwks(identity_service: IdentityService = Depends(get_identity_service)):
    """Publish public keys (JWKS) for verifying issued tokens."""
    return identity_service.jwks()


# ── Backwards-compatible development aliases ────────────────────────────────


@router.get("/dev/principals")
async def list_dev_principals(
    identity_service: IdentityService = Depends(get_identity_service),
):
    if not identity_service.registry.has("dev"):
        return []
    provider = identity_service.registry.get("dev")
    return provider.list_principals()


@router.post("/dev/login")
async def dev_login(
    body: LoginRequest,
    response: Response,
    identity_service: IdentityService = Depends(get_identity_service),
):
    """Alias for ``POST /auth/login`` with ``method="dev"``.

    Returns the session view directly (the shape the existing frontend expects)
    and sets the session cookie.
    """
    credentials = dict(body.credentials)
    if body.userId and "userId" not in credentials:
        credentials["userId"] = body.userId

    try:
        result = await identity_service.login("dev", credentials)
    except ProviderNotFoundError as exc:
        raise GabrielAPIError(str(exc), status_code=400) from exc
    except AuthenticationFailedError as exc:
        raise AuthenticationError(str(exc)) from exc

    _set_session_cookie(
        response,
        identity_service,
        result.token.value,
        identity_service.settings.token_ttl_seconds,
    )
    return result.session


@router.get("/session")
async def get_current_session(
    request: Request,
    identity_service: IdentityService = Depends(get_identity_service),
):
    """Return the session view for the cookie/bearer token, or 401."""
    token = extract_bearer_token(request.headers.get("authorization"))
    if token is None:
        token = request.cookies.get(identity_service.settings.session_cookie_name)

    auth = await authenticate_token(identity_service, token)
    principal = auth.principal
    meta = principal.metadata or {}
    return {
        "user": {
            "id": meta.get("user_id"),
            "principal": str(principal.id),
            "displayName": principal.display_name,
            "email": meta.get("email"),
            "initials": principal.display_name[0].upper() if principal.display_name else "?",
            "avatarUrl": None,
            "roles": meta.get("roles", []),
        },
        "organization": {
            "id": principal.organization_id,
            "name": principal.organization_id,
            "slug": principal.organization_id,
        },
        "tenantId": principal.organization_id,
        "authMethod": meta.get("auth_method", "dev"),
    }
