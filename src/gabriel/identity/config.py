"""Identity configuration.

Environment-driven settings for the Identity Service. Kept deliberately small:
a frozen dataclass populated from environment variables. No external settings
framework — the simplest thing that works (Simplicity First).
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class IdentitySettings:
    """Runtime configuration for authentication and token issuance.

    Attributes:
        environment: Deployment environment (``development``, ``test``,
            ``staging``, ``production``). Development-only providers refuse to
            run when this is ``production``.
        token_ttl_seconds: Lifetime of issued access tokens.
        session_cookie_name: Name of the httpOnly session cookie set on login.
        session_cookie_secure: Whether the session cookie requires HTTPS.
        private_key_path: Optional path to a PEM private signing key. When unset
            an ephemeral key is generated at startup (fine for dev/test).
        public_key_path: Optional path to a PEM public verification key.
        dev_auth_enabled: Whether the development identity provider is wired.
            Forced off in production regardless of this flag.
    """

    environment: str = "development"
    token_ttl_seconds: int = 3600
    session_cookie_name: str = "gabriel_session"
    session_cookie_secure: bool = False
    private_key_path: str | None = None
    public_key_path: str | None = None
    dev_auth_enabled: bool = True

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    @classmethod
    def from_env(cls) -> "IdentitySettings":
        """Build settings from ``GABRIEL_*`` environment variables."""
        environment = os.getenv("GABRIEL_ENV", "development")
        is_prod = environment.strip().lower() == "production"
        return cls(
            environment=environment,
            token_ttl_seconds=_env_int("GABRIEL_JWT_TOKEN_TTL_SECONDS", 3600),
            session_cookie_name=os.getenv("GABRIEL_SESSION_COOKIE_NAME", "gabriel_session"),
            # Default secure cookies on in production, off otherwise.
            session_cookie_secure=_env_bool("GABRIEL_SESSION_COOKIE_SECURE", is_prod),
            private_key_path=os.getenv("GABRIEL_JWT_PRIVATE_KEY_PATH"),
            public_key_path=os.getenv("GABRIEL_JWT_PUBLIC_KEY_PATH"),
            # Dev auth is never enabled in production.
            dev_auth_enabled=(not is_prod) and _env_bool("GABRIEL_DEV_AUTH_ENABLED", True),
        )
