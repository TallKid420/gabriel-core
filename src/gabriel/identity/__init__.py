"""Gabriel Identity: Universal identity abstraction and cryptographic verification."""

from gabriel.identity.principal_id import PrincipalID
from gabriel.identity.models import PrincipalType, PrincipalStatus, Capability
from gabriel.identity.principal import Principal
from gabriel.identity.token import Token, TokenPayload
from gabriel.identity.keys import KeyManager
from gabriel.identity.auth import TokenService
from gabriel.identity.bootstrap import register_identity_resource_types
from gabriel.identity.config import IdentitySettings
from gabriel.identity.providers import (
    AuthenticationResult,
    DevIdentityProvider,
    IdentityProvider,
    ProductionIdentityProvider,
    ProviderRegistry,
)
from gabriel.identity.identity_service import (
    IdentityService,
    LoginResult,
    build_default_identity_service,
    build_key_manager,
)
from gabriel.identity.exceptions import (
    IdentityError,
    InvalidPrincipalIDError,
    PrincipalNotFoundError,
    TokenGenerationError,
    TokenVerificationError,
    InvalidSignatureError,
    ExpiredTokenError,
    InvalidOrgError,
    AuthenticationFailedError,
    ProviderNotFoundError,
    IdentityConfigurationError,
)

__all__ = [
    "PrincipalID",
    "PrincipalType",
    "PrincipalStatus",
    "Capability",
    "Principal",
    "Token",
    "TokenPayload",
    "KeyManager",
    "TokenService",
    "register_identity_resource_types",
    "IdentitySettings",
    "IdentityProvider",
    "AuthenticationResult",
    "DevIdentityProvider",
    "ProductionIdentityProvider",
    "ProviderRegistry",
    "IdentityService",
    "LoginResult",
    "build_default_identity_service",
    "build_key_manager",
    "IdentityError",
    "InvalidPrincipalIDError",
    "PrincipalNotFoundError",
    "TokenGenerationError",
    "TokenVerificationError",
    "InvalidSignatureError",
    "ExpiredTokenError",
    "InvalidOrgError",
    "AuthenticationFailedError",
    "ProviderNotFoundError",
    "IdentityConfigurationError",
]
