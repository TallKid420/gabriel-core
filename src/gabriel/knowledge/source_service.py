"""Knowledge source lifecycle service.

Business logic for KnowledgeSource resources: creation through the
ResourceFactory (ADR-009 uniform GRN minting), org-scoped reads, paginated
listing, mutation with version bumps, soft deletion, and document
attachment/detachment. Every mutation appends a domain event within the same
transaction (ADR-017 transactional outbox).

Attachment model (V1): a document belongs to at most one knowledge source.
Attaching sets ``Document.knowledge_source_grn`` and re-labels the document's
chunks so vector search can filter by source; detaching clears both.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from gabriel.document.library import DocumentLibraryService
from gabriel.document.models import Document
from gabriel.document.repository import DocumentRepository
from gabriel.events.event import Event
from gabriel.events.repository import EventRepository
from gabriel.knowledge.source_mappers import domain_to_orm, orm_to_domain
from gabriel.knowledge.source_models import KnowledgeSource, KnowledgeSourceStatus
from gabriel.knowledge.source_repository import KnowledgeSourceRepository
from gabriel.knowledge.vector_store import ChunkVectorStore
from gabriel.resource.bootstrap import register_core_resource_types
from gabriel.resource.factory import ResourceFactory
from gabriel.resource.grn import GRN
from gabriel.resource.models import ResourceState
from gabriel.resource.registry import registry


class KnowledgeSourceService:
    """Business logic for knowledge sources (org-scoped)."""

    def __init__(self, session: AsyncSession, event_repo: EventRepository | None = None):
        register_core_resource_types()
        self.session = session
        self.repo = KnowledgeSourceRepository(session)
        self.event_repo = event_repo or EventRepository(session)
        self.factory = ResourceFactory(registry)
        self.documents = DocumentLibraryService(session, event_repo=self.event_repo)
        self.vectors = ChunkVectorStore(session)

    # ------------------------------------------------------------------ CRUD

    async def create_source(
        self,
        org_id: str,
        name: str,
        *,
        created_by: str,
        description: str = "",
        metadata: dict[str, Any] | None = None,
        labels: dict[str, str] | None = None,
        correlation_id: str | None = None,
        commit: bool = True,
    ) -> KnowledgeSource:
        """Create a knowledge source and append its creation event atomically."""
        grn = GRN.generate(org_id=org_id, resource_type="knowledge_source")
        source: KnowledgeSource = self.factory.create(
            "knowledge_source",
            grn=grn,
            org_id=org_id,
            state=ResourceState.ACTIVE,
            created_by=created_by,
            updated_by=created_by,
            name=name,
            description=description,
            status=KnowledgeSourceStatus.ACTIVE,
            document_count=0,
            metadata=metadata or {},
            labels=labels or {},
        )
        orm = await self.repo.create(domain_to_orm(source))
        await self.event_repo.append(
            Event(
                type="resource_created",
                principal_id=created_by,
                organization_id=org_id,
                resource_grn=str(grn),
                correlation_id=correlation_id,
                payload={
                    "resource_type": "knowledge_source",
                    "grn": str(grn),
                    "name": name,
                },
                metadata={
                    "service": "KnowledgeSourceService",
                    "operation": "create_source",
                },
            )
        )
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
        return orm_to_domain(orm)

    async def get_source(
        self, grn_str: str, org_id: str | None = None
    ) -> KnowledgeSource:
        return orm_to_domain(await self.repo.get_by_grn(grn_str, org_id=org_id))

    async def list_sources(
        self,
        org_id: str,
        *,
        status: KnowledgeSourceStatus | str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[KnowledgeSource], int]:
        """Paginated org-scoped listing; returns (items, total)."""
        status_value = (
            status.value if isinstance(status, KnowledgeSourceStatus) else status
        )
        orms, total = await self.repo.list_for_org(
            org_id, status=status_value, limit=limit, offset=offset
        )
        return [orm_to_domain(orm) for orm in orms], total

    async def update_source(
        self,
        grn_str: str,
        *,
        updated_by: str,
        org_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        status: KnowledgeSourceStatus | str | None = None,
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        commit: bool = True,
    ) -> KnowledgeSource:
        """Update mutable fields; bumps the resource version."""
        orm = await self.repo.get_by_grn(grn_str, org_id=org_id)
        if name is not None:
            orm.name = name
        if description is not None:
            orm.description = description
        if status is not None:
            normalized = (
                status
                if isinstance(status, KnowledgeSourceStatus)
                else KnowledgeSourceStatus(status)
            )
            orm.status = normalized.value
        if metadata is not None:
            orm.resource_metadata = {**(orm.resource_metadata or {}), **metadata}
        orm.version += 1
        orm.updated_by = updated_by
        await self.repo.update(orm)
        await self.event_repo.append(
            Event(
                type="resource_updated",
                principal_id=updated_by,
                organization_id=orm.org_id,
                resource_grn=orm.grn,
                correlation_id=correlation_id,
                payload={
                    "resource_type": "knowledge_source",
                    "grn": orm.grn,
                    "version": orm.version,
                },
                metadata={
                    "service": "KnowledgeSourceService",
                    "operation": "update_source",
                },
            )
        )
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
        return orm_to_domain(orm)

    async def delete_source(
        self,
        grn_str: str,
        *,
        deleted_by: str,
        org_id: str | None = None,
        correlation_id: str | None = None,
        commit: bool = True,
    ) -> KnowledgeSource:
        """Soft-delete a source and detach all its documents/chunks."""
        orm = await self.repo.get_by_grn(grn_str, org_id=org_id)

        # Detach member documents so RAG never resolves a deleted source.
        docs, _total = await DocumentRepository(self.session).list_for_org(
            orm.org_id, knowledge_source_grn=orm.grn, limit=10_000, offset=0
        )
        for doc in docs:
            doc.knowledge_source_grn = None
            await self.vectors.assign_knowledge_source(doc.grn, orm.org_id, None)

        orm.state = ResourceState.DELETED
        orm.version += 1
        orm.updated_by = deleted_by
        orm.document_count = 0
        await self.repo.update(orm)
        await self.event_repo.append(
            Event(
                type="resource_deleted",
                principal_id=deleted_by,
                organization_id=orm.org_id,
                resource_grn=orm.grn,
                correlation_id=correlation_id,
                payload={"resource_type": "knowledge_source", "grn": orm.grn},
                metadata={
                    "service": "KnowledgeSourceService",
                    "operation": "delete_source",
                },
            )
        )
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
        return orm_to_domain(orm)

    # ------------------------------------------------------- document links

    async def attach_document(
        self,
        source_grn: str,
        document_grn: str,
        *,
        org_id: str,
        updated_by: str,
        correlation_id: str | None = None,
        commit: bool = True,
    ) -> Document:
        """Attach a document (and its chunks) to a knowledge source."""
        source = await self.repo.get_by_grn(source_grn, org_id=org_id)
        document = await self.documents.update_document(
            document_grn,
            org_id=org_id,
            updated_by=updated_by,
            knowledge_source_grn=source.grn,
            correlation_id=correlation_id,
            commit=False,
        )
        await self.vectors.assign_knowledge_source(document_grn, org_id, source.grn)
        source.document_count = await self._count_documents(org_id, source.grn)
        await self.repo.update(source)
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
        return document

    async def detach_document(
        self,
        source_grn: str,
        document_grn: str,
        *,
        org_id: str,
        updated_by: str,
        correlation_id: str | None = None,
        commit: bool = True,
    ) -> Document:
        """Detach a document (and its chunks) from a knowledge source."""
        source = await self.repo.get_by_grn(source_grn, org_id=org_id)
        document = await self.documents.update_document(
            document_grn,
            org_id=org_id,
            updated_by=updated_by,
            knowledge_source_grn=None,
            correlation_id=correlation_id,
            commit=False,
        )
        await self.vectors.assign_knowledge_source(document_grn, org_id, None)
        source.document_count = await self._count_documents(org_id, source.grn)
        await self.repo.update(source)
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
        return document

    async def list_documents(
        self,
        source_grn: str,
        *,
        org_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Document], int]:
        """Paginated listing of documents attached to a source."""
        source = await self.repo.get_by_grn(source_grn, org_id=org_id)
        return await self.documents.list_documents(
            org_id, knowledge_source_grn=source.grn, limit=limit, offset=offset
        )

    async def _count_documents(self, org_id: str, source_grn: str) -> int:
        _docs, total = await DocumentRepository(self.session).list_for_org(
            org_id, knowledge_source_grn=source_grn, limit=1, offset=0
        )
        return int(total)
