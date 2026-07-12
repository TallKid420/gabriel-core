"""Message service.

Appends messages to conversations and lists them with pagination. Enforces the
domain invariants:

* the parent conversation must exist in the caller's organization;
* archived or deleted conversations do not accept new messages;
* ``total_tokens`` defaults to ``prompt_tokens + completion_tokens`` when the
  caller supplies both but omits the total.

Each append emits a ``message_created`` event in the same transaction
(ADR-017 transactional outbox).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from gabriel.conversation.message_mappers import domain_to_orm, orm_to_domain
from gabriel.conversation.message_models import Message, MessageRole
from gabriel.conversation.message_repository import MessageRepository
from gabriel.conversation.models import ConversationStatus
from gabriel.conversation.repository import ConversationRepository
from gabriel.events.event import Event
from gabriel.events.repository import EventRepository
from gabriel.resource.bootstrap import register_core_resource_types
from gabriel.resource.factory import ResourceFactory
from gabriel.resource.grn import GRN
from gabriel.resource.models import ResourceState
from gabriel.resource.registry import registry


class ConversationClosedError(Exception):
    """Raised when appending a message to an archived/deleted conversation."""


class MessageService:
    """Business logic for messages (conversation- and org-scoped)."""

    def __init__(self, session: AsyncSession, event_repo: EventRepository | None = None):
        register_core_resource_types()
        self.session = session
        self.repo = MessageRepository(session)
        self.conversations = ConversationRepository(session)
        self.event_repo = event_repo or EventRepository(session)
        self.factory = ResourceFactory(registry)

    async def create_message(
        self,
        conversation_grn: str,
        *,
        org_id: str,
        created_by: str,
        role: MessageRole | str,
        content: str,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        commit: bool = True,
    ) -> Message:
        """Append a message to a conversation, atomically with its event."""
        normalized_role = role if isinstance(role, MessageRole) else MessageRole(role)

        # Invariant: the conversation must exist in this org and be open.
        conversation = await self.conversations.get_by_grn(conversation_grn, org_id=org_id)
        if (
            conversation.status == ConversationStatus.ARCHIVED.value
            or conversation.state == ResourceState.DELETED
        ):
            raise ConversationClosedError(
                f"Conversation {conversation_grn} is closed for new messages"
            )

        if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
            total_tokens = prompt_tokens + completion_tokens

        grn = GRN.generate(org_id=org_id, resource_type="message")
        message: Message = self.factory.create(
            "message",
            grn=grn,
            org_id=org_id,
            state=ResourceState.ACTIVE,
            created_by=created_by,
            updated_by=created_by,
            conversation_grn=conversation_grn,
            role=normalized_role,
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            model=model,
            metadata=metadata or {},
        )
        orm = await self.repo.create(domain_to_orm(message))
        await self.event_repo.append(
            Event(
                type="message_created",
                principal_id=created_by,
                organization_id=org_id,
                resource_grn=str(grn),
                correlation_id=correlation_id,
                payload={
                    "resource_type": "message",
                    "grn": str(grn),
                    "conversation_grn": conversation_grn,
                    "role": normalized_role.value,
                    "model": model,
                    "total_tokens": total_tokens,
                },
                metadata={"service": "MessageService", "operation": "create_message"},
            )
        )
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
        return orm_to_domain(orm)

    async def get_message(self, grn_str: str, org_id: str | None = None) -> Message:
        return orm_to_domain(await self.repo.get_by_grn(grn_str, org_id=org_id))

    async def list_messages(
        self,
        conversation_grn: str,
        *,
        org_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Message], int]:
        """Paginated chronological listing; returns (items, total)."""
        orms, total = await self.repo.list_for_conversation(
            conversation_grn, org_id=org_id, limit=limit, offset=offset
        )
        return [orm_to_domain(orm) for orm in orms], total
