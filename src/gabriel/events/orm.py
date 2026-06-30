"""Event ORM: Persistent event model (ADR-017).

Implements the persisted event store using SQLAlchemy.
Events are append-only and form the immutable log of everything that happens
in Gabriel. This is the transactional outbox pattern seam for later
upgrade to Kafka/NATS without changing callers.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, JSON, String, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from gabriel.database.base import Base


class EventORM(Base):
    """Persistent event model.
    
    Events are immutable facts of what happened. Never updated or deleted,
    only appended. Indexed for efficient querying by organization, resource,
    correlation_id, and timestamp for audit trails and replay.
    """
    
    __tablename__ = "events"
    
    # Unique event ID (PK)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    """Unique event identifier (UUID as string)."""
    
    # Tenant isolation
    organization_id: Mapped[str] = mapped_column(
        String(128),
        index=True,
        nullable=False
    )
    """Organization this event belongs to (tenant isolation)."""
    
    # Event metadata
    type: Mapped[str] = mapped_column(String(128), nullable=False)
    """Event type (e.g., 'resource_created', 'organization_created')."""
    
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        index=True
    )
    """When the event occurred."""
    
    # Resource reference (nullable for org-level events)
    resource_grn: Mapped[str | None] = mapped_column(
        String(255),
        index=True,
        nullable=True
    )
    """The GRN of the resource this event concerns (nullable for org-level)."""
    
    # Principal who triggered this
    principal_id: Mapped[str] = mapped_column(String(255), nullable=False)
    """The Principal who triggered this event (principal://org/type/id)."""
    
    # Tracing
    correlation_id: Mapped[str | None] = mapped_column(
        String(36),
        index=True,
        nullable=True
    )
    """Trace ID for correlating related events (e.g., single request)."""
    
    causation_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True
    )
    """The event ID that caused this event (for causal ordering)."""
    
    # Extensible data
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        server_default="{}"
    )
    """Event-specific payload (resource type in payload for generic 'resource_created')."""
    
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "meta",
        JSON,
        nullable=False,
        server_default="{}"
    )
    """Extensible metadata (source_system, api_version, etc.)."""
    
    # Indexes for efficient querying
    __table_args__ = (
        Index("ix_events_org_occurred", "organization_id", "occurred_at"),
        Index("ix_events_resource_occurred", "resource_grn", "occurred_at"),
    )
