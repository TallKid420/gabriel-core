"""Conversation repository — persistence access for the Conversation resource.

All queries are org-scoped; tenant isolation is enforced at the query layer
(P-2: isolation by default). Listing is paginated (limit/offset) and returns
the total count so API responses can expose paging metadata.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gabriel.conversation.orm import ConversationORM
from gabriel.resource.exceptions import ResourceNotFoundError
from gabriel.resource.models import ResourceState


class ConversationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, orm: ConversationORM) -> ConversationORM:
        """Persist a new conversation row (caller controls the transaction)."""
        self.session.add(orm)
        await self.session.flush()
        return orm

    async def get_by_grn(
        self,
        grn: str,
        org_id: str | None = None,
        *,
        include_deleted: bool = False,
    ) -> ConversationORM:
        stmt = select(ConversationORM).filter_by(grn=grn)
        if org_id is not None:
            stmt = stmt.filter_by(org_id=org_id)
        if not include_deleted:
            stmt = stmt.filter(ConversationORM.state != ResourceState.DELETED)
        result = await self.session.execute(stmt)
        conversation = result.scalar_one_or_none()
        if not conversation:
            raise ResourceNotFoundError(f"Conversation {grn} not found")
        return conversation

    async def list_for_org(
        self,
        org_id: str,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> tuple[list[ConversationORM], int]:
        """Return (page, total) of conversations for an organization."""
        stmt = select(ConversationORM).filter_by(org_id=org_id)
        count_stmt = select(func.count(ConversationORM.grn)).filter_by(org_id=org_id)
        if status is not None:
            stmt = stmt.filter_by(status=status)
            count_stmt = count_stmt.filter_by(status=status)
        if not include_deleted:
            stmt = stmt.filter(ConversationORM.state != ResourceState.DELETED)
            count_stmt = count_stmt.filter(ConversationORM.state != ResourceState.DELETED)

        total = (await self.session.execute(count_stmt)).scalar_one()
        stmt = (
            stmt.order_by(ConversationORM.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), int(total)

    async def update(self, orm: ConversationORM) -> ConversationORM:
        """Flush pending changes on a managed ORM instance."""
        await self.session.flush()
        return orm
