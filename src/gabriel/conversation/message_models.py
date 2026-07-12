"""Message resource: a single turn inside a Conversation.

Messages are Universal Resources (GRN-addressed, org-owned) that belong to a
Conversation. They are immutable once written — corrections happen by
appending new messages, never by editing history (event-sourcing mindset).

Token accounting fields (``prompt_tokens``, ``completion_tokens``,
``total_tokens``) and ``model`` capture the LLM usage of assistant turns and
stay ``None`` for plain user/system turns.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from gabriel.resource.models import Resource, ResourceType


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class Message(Resource):
    """A single message within a conversation."""

    resource_type: ResourceType = ResourceType.MESSAGE

    conversation_grn: str
    """GRN of the parent conversation."""

    role: MessageRole
    """Who authored the turn: user, assistant, system, or tool."""

    content: str
    """Message text content."""

    prompt_tokens: int | None = None
    """Tokens consumed by the prompt (assistant turns)."""

    completion_tokens: int | None = None
    """Tokens produced by the completion (assistant turns)."""

    total_tokens: int | None = None
    """Total tokens for the turn; defaults to prompt + completion when set."""

    model: str | None = None
    """Model identifier used to produce the message, if applicable."""

    def public_view(self) -> dict[str, Any]:
        """Serializable representation safe to return from the API."""
        return {
            "grn": str(self.grn),
            "org_id": self.org_id,
            "conversation_grn": self.conversation_grn,
            "role": self.role.value,
            "content": self.content,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "model": self.model,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
            "metadata": self.metadata,
        }
