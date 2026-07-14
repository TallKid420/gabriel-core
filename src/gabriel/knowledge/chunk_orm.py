"""Persistence model for document chunks (Phase 4 — Document & Knowledge).

Chunks are NOT Universal Resources: they are derived data owned by their
source document (identified by ``document_grn``) and are hard-deleted when the
document is re-processed or removed.

The ``embedding`` column is declared JSON at the ORM level so SQLite tests
work unchanged; the Alembic migration converts it to pgvector ``vector(768)``
on PostgreSQL (768 dims = nomic-embed-text, the default Ollama embedding
model). This mirrors ``MemoryEntryORM.embedding``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from gabriel.database.base import Base, utcnow


class DocumentChunkORM(Base):
    """One embedded window of a document's normalized text."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        # Retrieval is always tenant-scoped; source filters narrow further.
        Index("ix_document_chunks_org_source", "org_id", "knowledge_source_grn"),
        Index("ix_document_chunks_org_document", "org_id", "document_grn"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    document_grn: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    knowledge_source_grn: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # JSON here; vector(768) on PostgreSQL (see migration k1e5f7a9b3c4).
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
