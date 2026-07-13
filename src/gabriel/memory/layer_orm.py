"""Persistence model for the MemoryLayerEntry resource.

Table ``memory_layer_entries`` — separate from the runtime working-memory
table ``memory_entries`` (see ``gabriel.memory.orm``), because layer entries
are governed Universal Resources with the full lifecycle/audit column set.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from gabriel.database.base import Base, GabrielResourceMixin


class MemoryLayerEntryORM(Base, GabrielResourceMixin):
    """Memory layer entry table — governed key/value memory metadata."""

    __tablename__ = "memory_layer_entries"
    __table_args__ = (
        # A key is unique within its (org, scope, subject) namespace.
        UniqueConstraint(
            "org_id", "scope", "subject_grn", "key",
            name="uq_memory_layer_entries_namespace_key",
        ),
        Index("ix_memory_layer_entries_org_scope", "org_id", "scope"),
    )

    key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="org")
    subject_grn: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
