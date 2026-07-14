"""Document repository — persistence access for the Document resource.

All queries are org-scoped (P-2: isolation by default). Listing is paginated
(limit/offset) and returns the total count so API responses can expose paging
metadata. Soft-deleted documents are hidden unless explicitly requested.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gabriel.document.orm import DocumentORM
from gabriel.resource.exceptions import ResourceNotFoundError
from gabriel.resource.models import ResourceState


class DocumentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, orm: DocumentORM) -> DocumentORM:
        """Persist a new document row (caller controls the transaction)."""
        self.session.add(orm)
        await self.session.flush()
        return orm

    async def get_by_grn(
        self,
        grn: str,
        org_id: str | None = None,
        *,
        include_deleted: bool = False,
    ) -> DocumentORM:
        stmt = select(DocumentORM).filter_by(grn=grn)
        if org_id is not None:
            stmt = stmt.filter_by(org_id=org_id)
        if not include_deleted:
            stmt = stmt.filter(DocumentORM.state != ResourceState.DELETED)
        result = await self.session.execute(stmt)
        document = result.scalar_one_or_none()
        if not document:
            raise ResourceNotFoundError(f"Document {grn} not found")
        return document

    async def list_for_org(
        self,
        org_id: str,
        *,
        status: str | None = None,
        knowledge_source_grn: str | None = None,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> tuple[list[DocumentORM], int]:
        """Return (page, total) of documents for an organization."""
        stmt = select(DocumentORM).filter_by(org_id=org_id)
        count_stmt = select(func.count(DocumentORM.grn)).filter_by(org_id=org_id)
        if status is not None:
            stmt = stmt.filter_by(status=status)
            count_stmt = count_stmt.filter_by(status=status)
        if knowledge_source_grn is not None:
            stmt = stmt.filter_by(knowledge_source_grn=knowledge_source_grn)
            count_stmt = count_stmt.filter_by(knowledge_source_grn=knowledge_source_grn)
        if not include_deleted:
            stmt = stmt.filter(DocumentORM.state != ResourceState.DELETED)
            count_stmt = count_stmt.filter(DocumentORM.state != ResourceState.DELETED)

        total = (await self.session.execute(count_stmt)).scalar_one()
        stmt = (
            stmt.order_by(DocumentORM.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), int(total)

    async def update(self, orm: DocumentORM) -> DocumentORM:
        """Flush pending changes on a managed ORM instance."""
        await self.session.flush()
        return orm
