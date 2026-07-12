"""Notification repository — persistence access for the Notification resource.

Queries are scoped by organization AND recipient (tenant isolation plus
recipient privacy: a user only ever sees their own notifications).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from gabriel.notification.orm import NotificationORM
from gabriel.resource.exceptions import ResourceNotFoundError


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class NotificationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, orm: NotificationORM) -> NotificationORM:
        """Persist a new notification row (caller controls the transaction)."""
        self.session.add(orm)
        await self.session.flush()
        return orm

    async def get_by_grn(
        self, grn: str, org_id: str | None = None, recipient: str | None = None
    ) -> NotificationORM:
        stmt = select(NotificationORM).filter_by(grn=grn)
        if org_id is not None:
            stmt = stmt.filter_by(org_id=org_id)
        if recipient is not None:
            stmt = stmt.filter_by(recipient=recipient)
        result = await self.session.execute(stmt)
        notification = result.scalar_one_or_none()
        if not notification:
            raise ResourceNotFoundError(f"Notification {grn} not found")
        return notification

    async def list_for_recipient(
        self,
        org_id: str,
        recipient: str,
        *,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[NotificationORM], int]:
        """Return (page, total) of a recipient's notifications, newest first."""
        stmt = select(NotificationORM).filter_by(org_id=org_id, recipient=recipient)
        count_stmt = select(func.count(NotificationORM.grn)).filter_by(
            org_id=org_id, recipient=recipient
        )
        if unread_only:
            stmt = stmt.filter_by(read=False)
            count_stmt = count_stmt.filter_by(read=False)

        total = (await self.session.execute(count_stmt)).scalar_one()
        stmt = (
            stmt.order_by(NotificationORM.created_at.desc()).limit(limit).offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), int(total)

    async def unread_count(self, org_id: str, recipient: str) -> int:
        result = await self.session.execute(
            select(func.count(NotificationORM.grn)).filter_by(
                org_id=org_id, recipient=recipient, read=False
            )
        )
        return int(result.scalar_one())

    async def mark_all_read(self, org_id: str, recipient: str) -> int:
        """Mark every unread notification of a recipient as read; returns count."""
        result = await self.session.execute(
            update(NotificationORM)
            .where(
                NotificationORM.org_id == org_id,
                NotificationORM.recipient == recipient,
                NotificationORM.read.is_(False),
            )
            .values(read=True, read_at=utcnow())
        )
        return int(result.rowcount or 0)
