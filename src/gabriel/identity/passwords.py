"""Password hashing for the password identity provider.

Uses PBKDF2-HMAC-SHA256 from the standard library (no external dependency).
The encoded format is self-describing so the algorithm and cost parameters can
be upgraded without invalidating existing hashes (hashes are re-verified with
the parameters recorded alongside them):

    pbkdf2_sha256$<iterations>$<salt_b64>$<digest_b64>

Design notes
------------
* ``verify_password`` uses a constant-time comparison to avoid timing attacks.
* ``needs_rehash`` lets the login path transparently upgrade weak/legacy hashes
  after a successful verification.
* Swapping to Argon2/bcrypt later only requires adding a new prefix handler —
  the stored format keeps old hashes verifiable during the transition
  (hot-swappable, mirroring the identity-provider strategy pattern).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 600_000
_SALT_BYTES = 16
_DIGEST = "sha256"


class PasswordHashError(ValueError):
    """Raised when a stored password hash is malformed or unsupported."""


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(encoded: str) -> bytes:
    padding = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(encoded + padding)


def hash_password(password: str, *, iterations: int = DEFAULT_ITERATIONS) -> str:
    """Hash ``password`` and return the self-describing encoded string."""
    if not password:
        raise ValueError("Password must not be empty")
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(_DIGEST, password.encode("utf-8"), salt, iterations)
    return f"{ALGORITHM}${iterations}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    """Return True if ``password`` matches the stored ``encoded`` hash."""
    if not password or not encoded:
        return False
    try:
        algorithm, iterations_str, salt_b64, digest_b64 = encoded.split("$")
        if algorithm != ALGORITHM:
            raise PasswordHashError(f"Unsupported password hash algorithm: {algorithm}")
        iterations = int(iterations_str)
        salt = _b64decode(salt_b64)
        expected = _b64decode(digest_b64)
    except PasswordHashError:
        raise
    except (ValueError, TypeError):
        # A malformed stored hash must fail verification, not crash the
        # authentication flow (uniform "invalid credentials" behaviour).
        return False

    candidate = hashlib.pbkdf2_hmac(_DIGEST, password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate, expected)


def needs_rehash(encoded: str, *, iterations: int = DEFAULT_ITERATIONS) -> bool:
    """Return True if the stored hash uses weaker parameters than current policy."""
    try:
        algorithm, iterations_str, _, _ = encoded.split("$")
        return algorithm != ALGORITHM or int(iterations_str) < iterations
    except (ValueError, TypeError):
        return True
