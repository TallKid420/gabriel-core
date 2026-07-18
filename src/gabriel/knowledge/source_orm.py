"""Persistence model for the KnowledgeSource resource."""
from __future__ import annotations

from sqlalchemy import Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from gabriel.database.base import Base, GabrielResourceMixin


class KnowledgeSourceORM(Base, GabrielResourceMixin):
    """Knowledge source table — org-scoped document collections for RAG."""

    __tablename__ = "knowledge_sources"
    __table_args__ = (
        # Listing pattern: newest sources for an org first.
        Index("ix_knowledge_sources_org_created", "org_id", "created_at"),
    )

    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", index=True
    )
    # Kind of knowledge backing this source (vector_collection /
    # document_collection / external). Stored as the enum's string value.
    source_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="vector_collection", index=True
    )
    document_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
