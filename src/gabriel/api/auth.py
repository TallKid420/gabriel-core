"""API authentication helpers.

The API boundary authenticates every request by verifying a **signed JWT**
issued by the :class:`~gabriel.identity.identity_service.IdentityService`.

This replaces the previous development bypass (which trusted a raw
``principal://`` string in the Authorization header, allowing anyone to forge
any identity). Trusting only signed tokens satisfies ADR-007 (signed identity
tokens propagated to internal services) and P-3/ADR-019 (no trusted-internal
bypass).

Tokens are accepted from either the ``Authorization: Bearer <jwt>`` header
(programmatic clients, SDK) or the httpOnly session cookie (browser clients).
"""
from __future__ import annotations

from pydantic import BaseModel

from gabriel.api.errors import AuthenticationError  # noqa: F401  (re-exported)
from gabriel.identity.identity_service import IdentityService
from gabriel.identity.exceptions import (
    ExpiredTokenError,
    IdentityError,
    InvalidSignatureError,
)
from gabriel.identity.principal import Principal


class AuthenticatedPrincipal(BaseModel):
    """A verified principal plus the raw token it was recovered from."""

    principal: Principal
    token: str


def extract_bearer_token(authorization: str | None) -> str | None:
    """Return the bearer token from an Authorization header, or ``None``."""
    if not authorization:
        return None
    if not authorization.lower().startswith("bearer "):
        raise AuthenticationError("Authorization header must use Bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise AuthenticationError("Bearer token is empty")
    return token


async def authenticate_token(
    identity_service: IdentityService,
    token: str | None,
) -> AuthenticatedPrincipal:
    """Verify a signed token and recover the authenticated principal.

    Raises:
        AuthenticationError: If the token is missing, malformed, expired, or
            fails signature verification.
    """
    if not token:
        raise AuthenticationError("Missing authentication token")
    try:
        principal = await identity_service.authenticate_request_token(token)
    except ExpiredTokenError as exc:
        raise AuthenticationError("Session token has expired") from exc
    except InvalidSignatureError as exc:
        raise AuthenticationError("Session token signature is invalid") from exc
    except IdentityError as exc:
        raise AuthenticationError(f"Invalid session token: {exc}") from exc

    return AuthenticatedPrincipal(principal=principal, token=token)
