"""Memory layer entry repository.

All queries are org-scoped (P-2: isolation by default). Expired entries are
filtered out of reads at the query layer.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from gabriel.memory.layer_orm import MemoryLayerEntryORM
from gabriel.resource.exceptions import ResourceNotFoundError


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _not_expired():
    return or_(
        MemoryLayerEntryORM.expires_at.is_(None),
        MemoryLayerEntryORM.expires_at > utcnow(),
    )


class MemoryLayerRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, orm: MemoryLayerEntryORM) -> MemoryLayerEntryORM:
        """Persist a new entry row (caller controls the transaction)."""
        self.session.add(orm)
        await self.session.flush()
        return orm

    async def get_by_grn(
        self, grn: str, org_id: str | None = None, include_expired: bool = False
    ) -> MemoryLayerEntryORM:
        stmt = select(MemoryLayerEntryORM).filter_by(grn=grn)
        if org_id is not None:
            stmt = stmt.filter_by(org_id=org_id)
        if not include_expired:
            stmt = stmt.filter(_not_expired())
        result = await self.session.execute(stmt)
        entry = result.scalar_one_or_none()
        if not entry:
            raise ResourceNotFoundError(f"Memory entry {grn} not found")
        return entry

    async def find_by_key(
        self,
        org_id: str,
        key: str,
        *,
        scope: str | None = None,
        subject_grn: str | None = None,
    ) -> MemoryLayerEntryORM | None:
        stmt = select(MemoryLayerEntryORM).filter_by(org_id=org_id, key=key)
        if scope is not None:
            stmt = stmt.filter_by(scope=scope)
        if subject_grn is not None:
            stmt = stmt.filter_by(subject_grn=subject_grn)
        stmt = stmt.filter(_not_expired())
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_for_org(
        self,
        org_id: str,
        *,
        scope: str | None = None,
        subject_grn: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[MemoryLayerEntryORM], int]:
        """Return (page, total) of live (non-expired) entries for an org."""
        stmt = select(MemoryLayerEntryORM).filter_by(org_id=org_id)
        count_stmt = select(func.count(MemoryLayerEntryORM.grn)).filter_by(org_id=org_id)
        if scope is not None:
            stmt = stmt.filter_by(scope=scope)
            count_stmt = count_stmt.filter_by(scope=scope)
        if subject_grn is not None:
            stmt = stmt.filter_by(subject_grn=subject_grn)
            count_stmt = count_stmt.filter_by(subject_grn=subject_grn)
        stmt = stmt.filter(_not_expired())
        count_stmt = count_stmt.filter(_not_expired())

        total = (await self.session.execute(count_stmt)).scalar_one()
        stmt = (
            stmt.order_by(MemoryLayerEntryORM.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), int(total)

    async def delete(self, orm: MemoryLayerEntryORM) -> None:
        """Hard-delete a memory entry (memory purges must actually purge)."""
        await self.session.delete(orm)
        await self.session.flush()
