"""Key management for signing and verifying tokens."""
import os
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend


class KeyManager:
    """Manages RSA key pairs for cryptographic signing and verification.
    
    In production, these keys would be stored in a secrets manager (AWS Secrets Manager,
    HashiCorp Vault, etc.). For this prototype, we generate them at runtime and
    optionally persist them to files.
    """

    def __init__(self, private_key_pem: bytes | None = None, public_key_pem: bytes | None = None):
        """Initialize with existing keys or generate new ones.
        
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

    @property
    def private_key_pem(self) -> bytes:
        """Export private key as PEM."""
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    @property
    def public_key_pem(self) -> bytes:
        """Export public key as PEM."""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

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
        """Persist keys to PEM files.
        
        Args:
            private_key_path: Path to write private key.
            public_key_path: Path to write public key.
        """
        with open(private_key_path, "wb") as f:
            f.write(self.private_key_pem)
        with open(public_key_path, "wb") as f:
            f.write(self.public_key_pem)
