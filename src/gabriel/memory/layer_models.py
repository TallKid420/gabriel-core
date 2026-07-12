"""Memory layer entry resource: governed key/value memory metadata.

Distinct from the runtime memory subsystem (``memory_entries`` — MGE/pgvector
working storage), a :class:`MemoryLayerEntry` is a **Universal Resource**
(GRN-addressed, versioned, org-owned) that stores structured memory metadata:

* ``key``/``value`` — a JSON value addressed by a key;
* ``scope`` — which layer the entry lives in (global/org/user/agent/conversation);
* ``subject_grn`` — the user/agent/conversation the entry is attached to,
  when the scope is narrower than the organization;
* ``tags`` — free-form labels for retrieval;
* ``expires_at`` — optional TTL after which the entry is treated as gone.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import Field

from gabriel.resource.models import Resource, ResourceType


class MemoryScope(str, Enum):
    GLOBAL = "global"
    ORG = "org"
    USER = "user"
    AGENT = "agent"
    CONVERSATION = "conversation"


class MemoryLayerEntry(Resource):
    """A governed memory entry, scoped to an organization."""

    resource_type: ResourceType = ResourceType.MEMORY

    key: str
    """Lookup key, unique within (org, scope, subject)."""

    value: Any = None
    """Arbitrary JSON-serializable value."""

    scope: MemoryScope = MemoryScope.ORG
    """Layer the entry belongs to."""

    subject_grn: str | None = None
    """Optional user/agent/conversation GRN the entry is attached to."""

    tags: list[str] = Field(default_factory=list)
    """Free-form labels for retrieval and grouping."""

    expires_at: datetime | None = None
    """Optional expiry; expired entries are filtered from reads."""

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        reference = now or datetime.now(timezone.utc)
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at <= reference

    def public_view(self) -> dict[str, Any]:
        """Serializable representation safe to return from the API."""
        return {
            "grn": str(self.grn),
            "org_id": self.org_id,
            "key": self.key,
            "value": self.value,
            "scope": self.scope.value,
            "subject_grn": self.subject_grn,
            "tags": self.tags,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }
