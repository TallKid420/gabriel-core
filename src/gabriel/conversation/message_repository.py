"""Message repository — persistence access for the Message resource.

Messages are append-only; there is no update or delete path. Listing is
paginated per conversation in chronological order.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gabriel.conversation.message_orm import MessageORM
from gabriel.resource.exceptions import ResourceNotFoundError


class MessageRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, orm: MessageORM) -> MessageORM:
        """Persist a new message row (caller controls the transaction)."""
        self.session.add(orm)
        await self.session.flush()
        return orm

    async def get_by_grn(self, grn: str, org_id: str | None = None) -> MessageORM:
        stmt = select(MessageORM).filter_by(grn=grn)
        if org_id is not None:
            stmt = stmt.filter_by(org_id=org_id)
        result = await self.session.execute(stmt)
        message = result.scalar_one_or_none()
        if not message:
            raise ResourceNotFoundError(f"Message {grn} not found")
        return message

    async def list_for_conversation(
        self,
        conversation_grn: str,
        *,
        org_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[MessageORM], int]:
        """Return (page, total) of messages for a conversation, oldest first."""
        stmt = select(MessageORM).filter_by(conversation_grn=conversation_grn)
        count_stmt = select(func.count(MessageORM.grn)).filter_by(
            conversation_grn=conversation_grn
        )
        if org_id is not None:
            stmt = stmt.filter_by(org_id=org_id)
            count_stmt = count_stmt.filter_by(org_id=org_id)

        total = (await self.session.execute(count_stmt)).scalar_one()
        stmt = stmt.order_by(MessageORM.created_at.asc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), int(total)
