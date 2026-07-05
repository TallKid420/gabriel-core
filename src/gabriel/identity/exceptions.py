# TODO Add custom constructors only for exceptions where structured context is genuinely useful

class IdentityError(Exception):
    """Base exception for all Gabriel identity errors."""
    pass


class InvalidPrincipalIDError(IdentityError):
    """Raised when a PrincipalID is malformed or cannot be parsed."""
    pass


class PrincipalNotFoundError(IdentityError):
    """Raised when a principal cannot be located."""
    pass


class TokenGenerationError(IdentityError):
    """Raised when a token cannot be generated."""
    pass


class TokenVerificationError(IdentityError):
    """Raised when a token fails verification."""
    pass


class InvalidSignatureError(TokenVerificationError):
    """Raised when a token signature is invalid or tampered."""
    pass


class ExpiredTokenError(TokenVerificationError):
    """Raised when a token has expired."""
    pass


class InvalidOrgError(TokenVerificationError):
    """Raised when a token's organization does not match the verifier's organization."""
    pass


class AuthenticationFailedError(IdentityError):
    """Raised when a provider cannot authenticate the supplied credentials."""
    pass


class ProviderNotFoundError(IdentityError):
    """Raised when no authentication provider is registered for a method."""
    pass


class IdentityConfigurationError(IdentityError):
    """Raised on invalid/unsafe identity configuration (e.g. dev auth in production)."""
    pass
