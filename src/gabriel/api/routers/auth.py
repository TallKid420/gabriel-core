"""Authentication endpoints.

    POST /auth/login    — authenticate via a provider, issue a signed token
    POST /auth/logout   — clear the session cookie
    GET  /auth/me       — current authenticated principal
    GET  /auth/jwks     — public keys for verifying issued tokens

Backwards-compatible development aliases (``/auth/dev/login``,
``/auth/dev/principals``, ``/auth/session``) are preserved for the existing
frontend and are only functional while the dev provider is enabled.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from gabriel.api.auth import authenticate_token, extract_bearer_token
from gabriel.api.errors import AuthenticationError, GabrielAPIError
from gabriel.api.dependencies import get_identity_service
from gabriel.identity.exceptions import (
    AuthenticationFailedError,
    ProviderNotFoundError,
)
from gabriel.identity.identity_service import IdentityService

router = APIRouter(prefix="/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    """Login payload: a provider ``method`` plus method-specific credentials."""

    method: str = "dev"
    credentials: dict[str, Any] = Field(default_factory=dict)
    # Convenience: allow ``{"userId": "..."}`` at the top level for dev login.
    userId: str | None = None


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


@router.post("/login")
async def login(
    body: LoginRequest,
    response: Response,
    identity_service: IdentityService = Depends(get_identity_service),
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

    return {
        "access_token": result.token.value,
        "token_type": "bearer",
        "expires_at": result.token.expires_at.isoformat(),
        "session": result.session,
    }


@router.post("/logout")
async def logout(
    response: Response,
    identity_service: IdentityService = Depends(get_identity_service),
):
    """Invalidate the browser session by clearing the session cookie."""
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

    auth = authenticate_token(identity_service, token)
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

    auth = authenticate_token(identity_service, token)
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
