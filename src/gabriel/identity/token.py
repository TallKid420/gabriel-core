"""Token and TokenPayload: JWT-based cryptographic identity verification."""
from datetime import datetime, timezone, timedelta
from typing import Any

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TokenPayload(BaseModel):
    """The claims inside a signed token.
    
    When a TokenService verifies a token, it decodes the JWT and validates
    the signature, returning a TokenPayload as proof.
    """

    principal_id: str
    """PrincipalID as a string (principal://org/type/identifier)."""

    organization_id: str
    """The organization this token is bound to."""

    principal_type: str
    """Type of principal (user, agent, system_agent, service_account)."""

    display_name: str
    """Display name of the principal."""

    capabilities: list[str] = Field(default_factory=list)
    """List of capabilities as strings."""

    issued_at: datetime
    """When the token was issued (iat)."""

    expires_at: datetime
    """When the token expires (exp)."""

    metadata: dict[str, Any] = Field(default_factory=dict)
    """Additional claims."""

    def is_expired(self) -> bool:
        """Check if token is expired."""
        return utcnow() >= self.expires_at


class Token(BaseModel):
    """A signed, JWT-encoded token."""

    value: str
    """The JWT string."""

    issued_at: datetime
    """When this token was issued."""

    expires_at: datetime
    """When this token expires."""

    def __str__(self) -> str:
        return self.value
