"""Document content store abstractions and disk-backed implementation.

The storage root is configurable: pass ``root_dir`` explicitly or set the
``GABRIEL_CONTENT_ROOT`` environment variable (default ``.gabriel/content``).
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

DEFAULT_CONTENT_ROOT = ".gabriel/content"


def default_content_root() -> Path:
    """Resolve the configured content-store root directory."""
    return Path(os.environ.get("GABRIEL_CONTENT_ROOT", DEFAULT_CONTENT_ROOT))


class ContentStore(Protocol):
    """Stores normalized document content and returns a stable pointer."""

    def put_text(self, *, organization_id: str, content: str) -> str:
        """Persist normalized text and return a dereferenceable pointer."""

    def put_bytes(
        self, *, organization_id: str, content: bytes, suffix: str = ".bin"
    ) -> str:
        """Persist raw uploaded bytes and return a dereferenceable pointer."""


@dataclass(frozen=True)
class DiskContentStore:
    """Stores normalized content on local disk using content-addressed paths."""

    root_dir: Path

    @classmethod
    def from_env(cls) -> "DiskContentStore":
        """Build a store rooted at ``GABRIEL_CONTENT_ROOT`` (configurable)."""
        return cls(default_content_root())

    def put_text(self, *, organization_id: str, content: str) -> str:
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        org_dir = self.root_dir / organization_id / "documents"
        org_dir.mkdir(parents=True, exist_ok=True)

        path = org_dir / f"{digest}.txt"
        if not path.exists():
            path.write_text(content, encoding="utf-8")

        # Pointer format is implementation-agnostic and explicit about backend.
        return f"disk://{organization_id}/documents/{digest}.txt"

    def put_bytes(
        self, *, organization_id: str, content: bytes, suffix: str = ".bin"
    ) -> str:
        """Persist raw uploaded bytes (content-addressed, per-org)."""
        digest = hashlib.sha256(content).hexdigest()
        org_dir = self.root_dir / organization_id / "raw"
        org_dir.mkdir(parents=True, exist_ok=True)

        name = f"{digest}{suffix or '.bin'}"
        path = org_dir / name
        if not path.exists():
            path.write_bytes(content)
        return f"disk://{organization_id}/raw/{name}"

    def read_text(self, pointer: str) -> str:
        """Read normalized text for a previously returned disk pointer."""
        return self._resolve(pointer).read_text(encoding="utf-8")

    def read_bytes(self, pointer: str) -> bytes:
        """Read raw bytes for a previously returned disk pointer."""
        return self._resolve(pointer).read_bytes()

    def _resolve(self, pointer: str) -> Path:
        prefix = "disk://"
        if not pointer.startswith(prefix):
            raise ValueError(f"Unsupported pointer scheme in '{pointer}'")
        relative = pointer[len(prefix) :]
        return self.root_dir / Path(relative)