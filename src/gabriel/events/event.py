"""Event model: The immutable fact of something that happened."""
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Event(BaseModel):
    """An immutable event that represents something that happened.
    
    Events are never updated or deleted — only appended to the event store.
    They form the append-only log of everything that happens in Gabriel.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    """Unique event identifier."""

    type: str
    """Event type (e.g., 'organization_created', 'agent_executed')."""

    occurred_at: datetime = Field(default_factory=utcnow)
    """When the event occurred."""

    principal_id: str
    """The Principal who triggered this event (principal://org/type/id)."""

    organization_id: str
    """The organization this event belongs to (tenant isolation)."""

    resource_grn: str | None = None
    """The Resource this event concerns (grn://...). Null for org-level events."""

    correlation_id: str | None = None
    """Trace ID for correlating related events (e.g., all events from one user request)."""

    causation_id: str | None = None
    """The event ID that caused this event (for causal ordering)."""

    payload: dict[str, Any] = Field(default_factory=dict)
    """The event-specific data."""

    metadata: dict[str, Any] = Field(default_factory=dict)
    """Extensible metadata (e.g., source_system, api_version)."""

    # Immutable
    model_config = {"frozen": True}

    def __str__(self) -> str:
        return f"Event(type={self.type}, id={self.id})"

    def __repr__(self) -> str:
        return f"Event(type={self.type!r}, id={self.id!r}, principal={self.principal_id!r})"
