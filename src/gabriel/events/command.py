"""Command model: The intent to do something (that may fail)."""
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Command(BaseModel):
    """A command representing intent to take an action.
    
    Unlike Events (which already happened and never fail),
    Commands are intent that may fail validation or execution.
    
    The dispatcher routes commands to handlers, which emit events
    if successful or raise exceptions if they fail.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    """Unique command identifier."""

    type: str
    """Command type (e.g., 'create_organization', 'execute_agent')."""

    principal_id: str
    """The Principal issuing this command."""

    organization_id: str
    """The organization context (tenant isolation)."""

    issued_at: datetime = Field(default_factory=utcnow)
    """When the command was issued."""

    correlation_id: str | None = None
    """Optional trace ID for correlating related commands/events."""

    payload: dict[str, Any] = Field(default_factory=dict)
    """The command-specific data (parameters)."""

    metadata: dict[str, Any] = Field(default_factory=dict)
    """Extensible metadata."""

    # Immutable
    model_config = {"frozen": True}

    def __str__(self) -> str:
        return f"Command(type={self.type}, id={self.id})"

    def __repr__(self) -> str:
        return f"Command(type={self.type!r}, id={self.id!r}, principal={self.principal_id!r})"
