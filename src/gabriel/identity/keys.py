"""Key management for signing and verifying tokens.

Supports JWKS publication and seamless key rotation (ADR-007: "rotation must be
seamless"). The active key signs new tokens; previously-active keys are retained
for verification so tokens issued before a rotation remain valid until they
expire.
"""
import base64
import hashlib
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend


def _b64url_uint(value: int) -> str:
    """Encode an unsigned integer as base64url (no padding), per RFC 7518."""
    length = (value.bit_length() + 7) // 8
    data = value.to_bytes(length, "big") if length else b"\x00"
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _compute_kid(public_key) -> str:
    """Compute a stable key id via the RFC 7638 JWK thumbprint."""
    numbers = public_key.public_numbers()
    thumbprint_input = json.dumps(
        {
            "e": _b64url_uint(numbers.e),
            "kty": "RSA",
            "n": _b64url_uint(numbers.n),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    digest = hashlib.sha256(thumbprint_input).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class KeyManager:
    """Manages RSA key pairs for cryptographic signing and verification.

    In production, keys would be loaded from a secrets manager (AWS Secrets
    Manager, HashiCorp Vault, etc.) via ``from_files`` or PEM bytes. For local
    development and tests, an ephemeral key pair is generated at runtime.

    The active key (``self.private_key`` / ``self.public_key``) signs new tokens.
    All public keys ever held — active plus rotated-out — are retained in the
    verification set (keyed by ``kid``) and published via :meth:`jwks`.
    """

    def __init__(self, private_key_pem: bytes | None = None, public_key_pem: bytes | None = None):
        """Initialize with existing keys or generate a new pair.

        Args:
            private_key_pem: PEM-encoded private key (if None, generates new).
            public_key_pem: PEM-encoded public key (optional; derived from private if None).
        """
        if private_key_pem:
            self.private_key = serialization.load_pem_private_key(
                private_key_pem,
                password=None,
                backend=default_backend(),
            )
        else:
            # Generate a new 2048-bit RSA key pair
            self.private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend(),
            )

        if public_key_pem:
            self.public_key = serialization.load_pem_public_key(
                public_key_pem,
                backend=default_backend(),
            )
        else:
            self.public_key = self.private_key.public_key()

        self.kid = _compute_kid(self.public_key)
        # Verification set: kid -> public key (active + previously-active keys).
        self._verification_keys: dict[str, object] = {self.kid: self.public_key}

    @property
    def private_key_pem(self) -> bytes:
        """Export the active private key as PEM."""
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    @property
    def public_key_pem(self) -> bytes:
        """Export the active public key as PEM."""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def get_verification_key(self, kid: str | None):
        """Return the public key for a given ``kid``.

        When ``kid`` is omitted (legacy tokens without a header kid) the active
        key is returned. Returns ``None`` when the kid is unknown.
        """
        if kid is None:
            return self.public_key
        return self._verification_keys.get(kid)

    def rotate(self) -> str:
        """Generate a new active signing key, retaining the old one for verification.

        Returns:
            The ``kid`` of the new active key.
        """
        new_private = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend(),
        )
        self.private_key = new_private
        self.public_key = new_private.public_key()
        self.kid = _compute_kid(self.public_key)
        # Keep the previous key(s) in the verification set for in-flight tokens.
        self._verification_keys[self.kid] = self.public_key
        return self.kid

    def jwks(self) -> dict:
        """Return a JWKS document exposing all public verification keys."""
        keys = []
        for kid, public_key in self._verification_keys.items():
            numbers = public_key.public_numbers()
            keys.append(
                {
                    "kty": "RSA",
                    "use": "sig",
                    "alg": "RS256",
                    "kid": kid,
                    "n": _b64url_uint(numbers.n),
                    "e": _b64url_uint(numbers.e),
                }
            )
        return {"keys": keys}

    @staticmethod
    def from_files(private_key_path: str, public_key_path: str) -> "KeyManager":
        """Load keys from PEM files.

        Args:
            private_key_path: Path to private key file.
            public_key_path: Path to public key file.

        Returns:
            KeyManager: Initialized with the loaded keys.
        """
        with open(private_key_path, "rb") as f:
            private_pem = f.read()
        with open(public_key_path, "rb") as f:
            public_pem = f.read()
        return KeyManager(private_key_pem=private_pem, public_key_pem=public_pem)

    def save_to_files(self, private_key_path: str, public_key_path: str) -> None:
        """Persist the active keys to PEM files.

        Args:
            private_key_path: Path to write private key.
            public_key_path: Path to write public key.
        """
        with open(private_key_path, "wb") as f:
            f.write(self.private_key_pem)
        with open(public_key_path, "wb") as f:
            f.write(self.public_key_pem)
