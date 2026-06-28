"""TokenService: JWT-based cryptographic identity verification.

Core flow:
  Principal → Issue Token → Verify Token → Recover Principal (as TokenPayload)
"""
from datetime import datetime, timedelta, timezone
import json

import jwt

from gabriel.identity.principal import Principal
from gabriel.identity.token import Token, TokenPayload
from gabriel.identity.keys import KeyManager
from gabriel.identity.exceptions import (
    TokenGenerationError,
    TokenVerificationError,
    InvalidSignatureError,
    ExpiredTokenError,
    InvalidOrgError,
)


class TokenService:
    """Issues and verifies JWT tokens for principals.
    
    Tokens are cryptographically signed with a private key and verified
    with a corresponding public key. A valid token proves identity.
    """

    ALGORITHM = "RS256"  # RSA with SHA-256
    TOKEN_EXPIRY_SECONDS = 3600  # 1 hour

    def __init__(
        self,
        key_manager: KeyManager,
        token_expiry_seconds: int | None = None,
    ):
        """Initialize TokenService.
        
        Args:
            key_manager: KeyManager with signing/verification keys.
            token_expiry_seconds: TTL for issued tokens (default: 1 hour).
        """
        self.key_manager = key_manager
        self.token_expiry_seconds = token_expiry_seconds or self.TOKEN_EXPIRY_SECONDS

    def issue(self, principal: Principal) -> Token:
        """Issue a signed JWT token for a principal.
        
        Args:
            principal: The principal to issue a token for.
            
        Returns:
            Token: A signed JWT token.
            
        Raises:
            TokenGenerationError: If token generation fails.
        """
        try:
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(seconds=self.token_expiry_seconds)

            payload = {
                "principal_id": str(principal.id),
                "organization_id": principal.organization_id,
                "principal_type": principal.principal_type.value,
                "display_name": principal.display_name,
                "capabilities": [cap.value for cap in principal.capabilities],
                "iat": now,
                "exp": expires_at,
                "metadata": principal.metadata,
            }

            token_value = jwt.encode(
                payload,
                self.key_manager.private_key,
                algorithm=self.ALGORITHM,
            )

            return Token(
                value=token_value,
                issued_at=now,
                expires_at=expires_at,
            )
        except Exception as exc:
            raise TokenGenerationError(f"Failed to generate token: {exc}") from exc

    def verify(self, token: Token | str, organization_id: str | None = None) -> TokenPayload:
        """Verify and decode a JWT token.
        
        Args:
            token: The token to verify (Token object or string).
            organization_id: Optional organization to verify token belongs to.
                If provided and doesn't match token's org, raises InvalidOrgError.
            
        Returns:
            TokenPayload: Decoded token claims.
            
        Raises:
            InvalidSignatureError: If signature is invalid or tampered.
            ExpiredTokenError: If token has expired.
            InvalidOrgError: If organization doesn't match (if organization_id provided).
            TokenVerificationError: For other verification failures.
        """
        try:
            token_str = token.value if isinstance(token, Token) else token

            # Decode and verify signature
            decoded = jwt.decode(
                token_str,
                self.key_manager.public_key,
                algorithms=[self.ALGORITHM],
            )

            # Parse into TokenPayload
            payload = TokenPayload(
                principal_id=decoded["principal_id"],
                organization_id=decoded["organization_id"],
                principal_type=decoded["principal_type"],
                display_name=decoded["display_name"],
                capabilities=decoded.get("capabilities", []),
                issued_at=datetime.fromtimestamp(decoded["iat"], tz=timezone.utc),
                expires_at=datetime.fromtimestamp(decoded["exp"], tz=timezone.utc),
                metadata=decoded.get("metadata", {}),
            )

            # Optional organization check
            if organization_id and payload.organization_id != organization_id:
                raise InvalidOrgError(
                    f"Token organization '{payload.organization_id}' "
                    f"does not match verifier organization '{organization_id}'"
                )

            return payload

        except jwt.ExpiredSignatureError as exc:
            raise ExpiredTokenError("Token has expired") from exc
        except jwt.InvalidSignatureError as exc:
            raise InvalidSignatureError("Token signature is invalid or tampered") from exc
        except (InvalidOrgError, ExpiredTokenError, InvalidSignatureError):
            raise
        except Exception as exc:
            raise TokenVerificationError(f"Failed to verify token: {exc}") from exc
