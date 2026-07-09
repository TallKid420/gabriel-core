"""Memory ORM: Persistent model for memory entries (ADR-012, ADR-014).

MemoryEntryORM is NOT a GabrielResourceMixin — memory entries are records
managed by the memory subsystem, not top-level governed Resources. They are
org-scoped and agent-scoped for tenant isolation, but don't carry the full
Resource lifecycle (draft/active/deprecated/deleted).

The ``embedding`` column is a pgvector ``vector(1536)`` in Postgres; the
migration enables the extension and creates the column with the correct type.
We declare it as JSON here so SQLAlchemy can read/write float lists; the
migration ALTER TABLE sets the real vector type for cosine-search to work.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, Index, JSON, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from gabriel.database.base import Base


class MemoryEntryORM(Base):
    """Persistent memory entry.

    Columns
    -------
    id          : UUID string — primary key.
    org_id      : Tenant isolation; all queries filter on this first.
    agent_id    : Optional — scopes the entry to a specific agent.
    layer       : MemoryLayer enum value (str).
    scope       : Granularity: "agent" | "session" | "org".
    content     : The stored text/serialised content.
    importance  : 0.0-1.0 signal for MGE promotion/demotion rules.
    metadata    : Arbitrary key-value bag (labels, source GRN, etc.).
    embedding   : pgvector float array for semantic search (nullable;
                  only populated for SEMANTIC layer entries).
    created_at  : Immutable creation timestamp.
    expires_at  : Optional TTL; MGE enforces purge after this time.
    """

    __tablename__ = "memory_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Tenant isolation — always filter by org_id first (P-2)
    org_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)

    # Optional agent scope
    agent_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)

    # Layer and scope (ADR-012)
    layer: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(64), nullable=False, server_default="agent")

    # Payload
    content: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[float] = mapped_column(Float, nullable=False, server_default="1.0")

    # Stored as JSON list in ORM; migration converts to vector(1536) in Postgres
    # for pgvector cosine similarity. NULL for non-semantic layers.
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)

    # Arbitrary metadata (source GRN, principal, custom labels)
    entry_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, server_default="{}"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    # Nullable — set by MGE or caller for TTL enforcement
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # Fast lookup: org + layer (most common retrieval pattern)
        Index("ix_memory_entries_org_layer", "org_id", "layer"),
        # Agent-scoped queries
        Index("ix_memory_entries_agent_layer", "agent_id", "layer"),
    )
