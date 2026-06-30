"""Resource read-model projection table (CQRS read side)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, JSON, String, text
from sqlalchemy.orm import Mapped, mapped_column

from gabriel.database.base import Base


class ResourceProjectionORM(Base):
    """Materialized resource state for O(1) lookups and fast listing."""

    __tablename__ = "resource_projections"

    grn: Mapped[str] = mapped_column(String(255), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, server_default="{}")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, server_default="{}")
    last_event_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_event_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("ix_resource_projections_org_type", "organization_id", "resource_type"),
        Index("ix_resource_projections_org_state", "organization_id", "state"),
    )