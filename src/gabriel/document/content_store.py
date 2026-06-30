"""Document content store abstractions and disk-backed implementation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class ContentStore(Protocol):
    """Stores normalized document content and returns a stable pointer."""

    def put_text(self, *, organization_id: str, content: str) -> str:
        """Persist normalized text and return a dereferenceable pointer."""


@dataclass(frozen=True)
class DiskContentStore:
    """Stores normalized content on local disk using content-addressed paths."""

    root_dir: Path

    def put_text(self, *, organization_id: str, content: str) -> str:
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        org_dir = self.root_dir / organization_id / "documents"
        org_dir.mkdir(parents=True, exist_ok=True)

        path = org_dir / f"{digest}.txt"
        if not path.exists():
            path.write_text(content, encoding="utf-8")

        # Pointer format is implementation-agnostic and explicit about backend.
        return f"disk://{organization_id}/documents/{digest}.txt"

    def read_text(self, pointer: str) -> str:
        """Read normalized text for a previously returned disk pointer."""
        prefix = "disk://"
        if not pointer.startswith(prefix):
            raise ValueError(f"Unsupported pointer scheme in '{pointer}'")

        relative = pointer[len(prefix) :]
        target = self.root_dir / Path(relative)
        return target.read_text(encoding="utf-8")