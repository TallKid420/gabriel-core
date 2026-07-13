"""Conversation lifecycle service.

Business logic for Conversation resources: creation through the
ResourceFactory (ADR-009 uniform GRN minting), org-scoped reads, paginated
listing, mutation with version bumps, and soft deletion. Every mutation
appends a domain event within the same transaction (ADR-017 transactional
outbox).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from gabriel.conversation.mappers import domain_to_orm, orm_to_domain
from gabriel.conversation.models import Conversation, ConversationStatus
from gabriel.conversation.repository import ConversationRepository
from gabriel.events.event import Event
from gabriel.events.repository import EventRepository
from gabriel.resource.bootstrap import register_core_resource_types
from gabriel.resource.factory import ResourceFactory
from gabriel.resource.grn import GRN
from gabriel.resource.models import ResourceState
from gabriel.resource.registry import registry


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ConversationService:
    """Business logic for conversations (org-scoped)."""

    def __init__(self, session: AsyncSession, event_repo: EventRepository | None = None):
        register_core_resource_types()
        self.session = session
        self.repo = ConversationRepository(session)
        self.event_repo = event_repo or EventRepository(session)
        self.factory = ResourceFactory(registry)

    async def create_conversation(
        self,
        org_id: str,
        title: str,
        *,
        created_by: str,
        participants: list[str] | None = None,
        agent_grn: str | None = None,
        metadata: dict[str, Any] | None = None,
        labels: dict[str, str] | None = None,
        correlation_id: str | None = None,
        commit: bool = True,
    ) -> Conversation:
        """Create a conversation and append its creation event atomically."""
        grn = GRN.generate(org_id=org_id, resource_type="conversation")
        conversation: Conversation = self.factory.create(
            "conversation",
            grn=grn,
            org_id=org_id,
            state=ResourceState.ACTIVE,
            created_by=created_by,
            updated_by=created_by,
            title=title,
            status=ConversationStatus.ACTIVE,
            participants=participants or [created_by],
            agent_grn=agent_grn,
            metadata=metadata or {},
            labels=labels or {},
        )
        orm = await self.repo.create(domain_to_orm(conversation))
        await self.event_repo.append(
            Event(
                type="resource_created",
                principal_id=created_by,
                organization_id=org_id,
                resource_grn=str(grn),
                correlation_id=correlation_id,
                payload={
                    "resource_type": "conversation",
                    "grn": str(grn),
                    "title": title,
                    "agent_grn": agent_grn,
                },
                metadata={"service": "ConversationService", "operation": "create_conversation"},
            )
        )
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
        return orm_to_domain(orm)

    async def get_conversation(self, grn_str: str, org_id: str | None = None) -> Conversation:
        return orm_to_domain(await self.repo.get_by_grn(grn_str, org_id=org_id))

    async def list_conversations(
        self,
        org_id: str,
        *,
        status: ConversationStatus | str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Conversation], int]:
        """Paginated org-scoped listing; returns (items, total)."""
        status_value = (
            status.value if isinstance(status, ConversationStatus) else status
        )
        orms, total = await self.repo.list_for_org(
            org_id, status=status_value, limit=limit, offset=offset
        )
        return [orm_to_domain(orm) for orm in orms], total

    async def update_conversation(
        self,
        grn_str: str,
        *,
        updated_by: str,
        org_id: str | None = None,
        title: str | None = None,
        status: ConversationStatus | str | None = None,
        participants: list[str] | None = None,
        agent_grn: str | None = None,
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> Conversation:
        """Update mutable fields; bumps the resource version."""
        orm = await self.repo.get_by_grn(grn_str, org_id=org_id)
        if title is not None:
            orm.title = title
        if status is not None:
            normalized = (
                status if isinstance(status, ConversationStatus) else ConversationStatus(status)
            )
            orm.status = normalized.value
        if participants is not None:
            orm.participants = participants
        if agent_grn is not None:
            orm.agent_grn = agent_grn
        if metadata is not None:
            orm.resource_metadata = {**orm.resource_metadata, **metadata}
        orm.version += 1
        orm.updated_by = updated_by
        await self.event_repo.append(
            Event(
                type="resource_updated",
                principal_id=updated_by,
                organization_id=orm.org_id,
                resource_grn=grn_str,
                correlation_id=correlation_id,
                payload={
                    "resource_type": "conversation",
                    "grn": grn_str,
                    "title": orm.title,
                    "status": orm.status,
                },
                metadata={"service": "ConversationService", "operation": "update_conversation"},
            )
        )
        await self.session.commit()
        return orm_to_domain(orm)

    async def archive_conversation(
        self,
        grn_str: str,
        *,
        archived_by: str,
        org_id: str | None = None,
        correlation_id: str | None = None,
    ) -> Conversation:
        """Convenience wrapper: set domain status to ARCHIVED."""
        return await self.update_conversation(
            grn_str,
            updated_by=archived_by,
            org_id=org_id,
            status=ConversationStatus.ARCHIVED,
            correlation_id=correlation_id,
        )

    async def delete_conversation(
        self,
        grn_str: str,
        *,
        deleted_by: str,
        org_id: str | None = None,
        correlation_id: str | None = None,
    ) -> Conversation:
        """Soft-delete: mark the conversation DELETED (audit trail preserved)."""
        orm = await self.repo.get_by_grn(grn_str, org_id=org_id)
        orm.state = ResourceState.DELETED
        orm.version += 1
        orm.updated_by = deleted_by
        await self.event_repo.append(
            Event(
                type="resource_deleted",
                principal_id=deleted_by,
                organization_id=orm.org_id,
                resource_grn=grn_str,
                correlation_id=correlation_id,
                payload={"resource_type": "conversation", "grn": grn_str},
                metadata={"service": "ConversationService", "operation": "delete_conversation"},
            )
        )
        await self.session.commit()
        return orm_to_domain(orm)
