"""Conversation resource: a threaded exchange between participants and an agent.

A Conversation is a Universal Resource (GRN-addressed, versioned, org-owned).
It groups Messages (see ``gabriel.conversation.message_models``) and references
the Agent that services it. Participants are recorded as GRN/principal-id
strings so both human users and agents can take part.

Archiving is a first-class domain state (``ConversationStatus``) distinct from
the generic Resource lifecycle: an archived conversation is still ACTIVE as a
resource (readable, auditable) but closed for new messages.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field

from gabriel.resource.models import Resource, ResourceType


class ConversationStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class Conversation(Resource):
    """A conversation thread, scoped to an organization."""

    resource_type: ResourceType = ResourceType.CONVERSATION

    title: str
    """Human-readable conversation title."""

    status: ConversationStatus = ConversationStatus.ACTIVE
    """Domain status: active (accepts messages) or archived (read-only)."""

    participants: list[str] = Field(default_factory=list)
    """Participant identifiers (user GRNs / principal ids / agent GRNs)."""

    agent_grn: str | None = None
    """GRN of the agent servicing this conversation, if any."""

    def public_view(self) -> dict[str, Any]:
        """Serializable representation safe to return from the API."""
        return {
            "grn": str(self.grn),
            "org_id": self.org_id,
            "title": self.title,
            "status": self.status.value,
            "participants": self.participants,
            "agent_grn": self.agent_grn,
            "state": self.state.value,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
            "metadata": self.metadata,
            "labels": self.labels,
        }
