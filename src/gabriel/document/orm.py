"""Persistence model for the Document resource (Phase 4)."""
from __future__ import annotations

from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from gabriel.database.base import Base, GabrielResourceMixin


class DocumentORM(Base, GabrielResourceMixin):
    """Documents table — org-scoped document library rows."""

    __tablename__ = "documents"
    __table_args__ = (
        # Listing pattern: newest documents for an org first.
        Index("ix_documents_org_created", "org_id", "created_at"),
    )

    filename: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    source_uri: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    byte_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_pointer: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    raw_pointer: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="uploaded", index=True
    )
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    knowledge_source_grn: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
