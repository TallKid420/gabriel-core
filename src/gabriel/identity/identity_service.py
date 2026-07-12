"""Identity Service: the authentication boundary.

This is the single place where authentication happens (ADR-007: "Authentication
is handled at the platform boundary ... and produces a signed identity token
that is propagated through all internal calls"). It:

* delegates credential verification to a pluggable :class:`IdentityProvider`,
* issues a signed JWT (:class:`TokenService`) carrying the principal's identity
  and capabilities,
* verifies session tokens on subsequent requests and reconstructs the
  :class:`Principal` from the signed claims — internal services trust this token
  and never re-authenticate.

It intentionally does **not** perform authorization; that is PEEL's job.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from gabriel.identity.auth import TokenService
from gabriel.identity.config import IdentitySettings
from gabriel.database.session import async_session
from gabriel.identity.exceptions import IdentityConfigurationError
from gabriel.identity.keys import KeyManager
from gabriel.identity.models import Capability, PrincipalStatus, PrincipalType
from gabriel.identity.principal import Principal
from gabriel.identity.principal_id import PrincipalID
from gabriel.identity.providers.base import IdentityProvider
from gabriel.identity.providers.dev import DevIdentityProvider
from gabriel.identity.providers.password import PasswordIdentityProvider
from gabriel.identity.providers.production import ProductionIdentityProvider
from gabriel.identity.providers.registry import ProviderRegistry
from gabriel.identity.token import Token, TokenPayload


class LoginResult:
    """Result of a successful login: the signed token plus a session view."""

    __slots__ = ("principal", "token", "session")

    def __init__(self, principal: Principal, token: Token, session: dict[str, Any]) -> None:
        self.principal = principal
        self.token = token
        self.session = session


class IdentityService:
    """Authenticates principals and issues/verifies signed session tokens."""

    def __init__(
        self,
        settings: IdentitySettings,
        key_manager: KeyManager,
        registry: ProviderRegistry,
        token_service: TokenService | None = None,
    ) -> None:
        self.settings = settings
        self.key_manager = key_manager
        self.registry = registry
        self.token_service = token_service or TokenService(
            key_manager, token_expiry_seconds=settings.token_ttl_seconds
        )

    # ── Authentication ─────────────────────────────────────────────────────

    async def login(self, method: str, credentials: Mapping[str, Any]) -> LoginResult:
        """Authenticate ``credentials`` via the ``method`` provider and issue a token.

        Raises:
            ProviderNotFoundError: If ``method`` has no registered provider.
            AuthenticationFailedError: If the credentials are invalid.
        """
        provider = self.registry.get(method)
        result = await provider.authenticate(credentials)
        token = self.token_service.issue(result.principal)

        session = dict(result.session)
        session["authMethod"] = session.get("authMethod", method)
        session["expiresAt"] = token.expires_at.isoformat()
        return LoginResult(principal=result.principal, token=token, session=session)

    # ── Session validation ─────────────────────────────────────────────────

    def verify_token(self, token: Token | str) -> TokenPayload:
        """Verify a signed token and return its claims (raises on failure)."""
        return self.token_service.verify(token)

    def principal_from_token(self, token: Token | str) -> Principal:
        """Verify a token and reconstruct the :class:`Principal` from its claims."""
        payload = self.token_service.verify(token)
        return self._principal_from_payload(payload)

    async def authenticate_request_token(self, token: Token | str) -> Principal:
        """Verify a request token and resolve the authenticated principal.

        Production requests are resolved through the persisted-principal provider.
        Non-production requests continue using signed claims directly.
        """
        token_str = token.value if isinstance(token, Token) else token
        if self.registry.has("production"):
            result = await self.registry.get("production").authenticate({"token": token_str})
            return result.principal
        return self.principal_from_token(token_str)

    @staticmethod
    def _principal_from_payload(payload: TokenPayload) -> Principal:
        capabilities = {Capability(cap) for cap in payload.capabilities}
        return Principal(
            id=PrincipalID.parse(payload.principal_id),
            organization_id=payload.organization_id,
            principal_type=PrincipalType(payload.principal_type),
            display_name=payload.display_name,
            status=PrincipalStatus.ACTIVE,
            capabilities=capabilities,
            metadata=payload.metadata,
        )

    # ── JWKS ────────────────────────────────────────────────────────────────

    def jwks(self) -> dict:
        """Return the JWKS document with public verification keys."""
        return self.key_manager.jwks()

    # ── Introspection ────────────────────────────────────────────────────────

    def available_methods(self) -> list[str]:
        return self.registry.methods()


def build_key_manager(settings: IdentitySettings) -> KeyManager:
    """Load signing keys from configured PEM files, or generate an ephemeral pair.

    An ephemeral key is fine for local development and tests (JWKS + verification
    stay consistent within the process). Production should mount real keys via
    ``GABRIEL_JWT_PRIVATE_KEY_PATH`` / ``GABRIEL_JWT_PUBLIC_KEY_PATH``.
    """
    if settings.private_key_path and settings.public_key_path:
        return KeyManager.from_files(settings.private_key_path, settings.public_key_path)
    return KeyManager()


def build_default_identity_service(
    settings: IdentitySettings | None = None,
    session_factory: Any | None = None,
) -> IdentityService:
    """Construct an IdentityService wired with the default provider set.

    The development provider is only registered outside production and when
    enabled. The password provider is registered whenever a database session
    factory is available (it is the first *real* method and works in every
    environment). In production with no real provider configured yet, the
    service still starts (JWKS/verification work); login reports no methods.

    Args:
        settings: Identity settings; defaults to environment-derived settings.
        session_factory: Async SQLAlchemy session factory used by DB-backed
            providers (password, production). Defaults to the module-level
            ``async_session`` factory.
    """
    settings = settings or IdentitySettings.from_env()
    if settings.is_production and settings.dev_auth_enabled:
        raise IdentityConfigurationError(
            "Dev identity provider is forbidden when GABRIEL_ENV=production"
        )

    key_manager = build_key_manager(settings)
    registry = ProviderRegistry()
    token_service = TokenService(
        key_manager, token_expiry_seconds=settings.token_ttl_seconds
    )
    db_sessions = session_factory or async_session

    providers: list[IdentityProvider] = []
    if settings.dev_auth_enabled and not settings.is_production:
        providers.append(DevIdentityProvider(settings))
    providers.append(PasswordIdentityProvider(db_sessions))
    if settings.is_production:
        providers.append(ProductionIdentityProvider(token_service, db_sessions))

    assert not settings.is_production or all(
        provider.name != "dev" for provider in providers
    )

    for provider in providers:
        registry.register(provider)

    return IdentityService(
        settings=settings,
        key_manager=key_manager,
        registry=registry,
        token_service=token_service,
    )
