"""Document library service (Phase 4 — Document & Knowledge).

DB-backed lifecycle for Document resources, following the Phase-2 vertical
slice pattern (Model → ORM → Mapper → Repository → Service → Router):

    upload bytes
        -> normalize to text (DocumentNormalizer: PDF/TXT/MD/DOCX/…)
        -> store raw bytes + normalized text on disk (configurable root)
        -> mint a GRN via the ResourceFactory (ADR-009)
        -> persist a ``documents`` row + append a domain event

Chunking/embedding is delegated to
:class:`gabriel.document.processing.DocumentProcessingService` so upload and
processing remain independently testable. The pre-existing event-sourced
``DocumentIngestionService`` is untouched.
"""
from __future__ import annotations

import hashlib
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extensions import uuid7

from gabriel.document.content_store import DiskContentStore
from gabriel.document.mappers import domain_to_orm, orm_to_domain
from gabriel.document.models import Document, DocumentStatus
from gabriel.document.normalizer import DocumentNormalizer
from gabriel.document.repository import DocumentRepository
from gabriel.events.event import Event
from gabriel.events.repository import EventRepository
from gabriel.logging_config import get_logger
from gabriel.knowledge.vector_store import ChunkVectorStore
from gabriel.resource.bootstrap import register_core_resource_types
from gabriel.resource.factory import ResourceFactory
from gabriel.resource.grn import GRN
from gabriel.resource.models import ResourceState
from gabriel.resource.registry import registry

SUPPORTED_UPLOAD_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown", ".docx"}
_TEMPFILE_UNLINK_RETRIES = 5
_TEMPFILE_UNLINK_BACKOFF_SECONDS = 0.05
logger = get_logger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UnsupportedDocumentTypeError(Exception):
    """The uploaded file extension is not accepted by the library."""


class DocumentLibraryService:
    """Business logic for the org-scoped document library."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        event_repo: EventRepository | None = None,
        normalizer: DocumentNormalizer | None = None,
        content_store: DiskContentStore | None = None,
    ):
        register_core_resource_types()
        self.session = session
        self.repo = DocumentRepository(session)
        self.event_repo = event_repo or EventRepository(session)
        self.factory = ResourceFactory(registry)
        self.normalizer = normalizer or DocumentNormalizer()
        self.content_store = content_store or DiskContentStore.from_env()

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    async def upload_document(
        self,
        org_id: str,
        *,
        filename: str,
        content: bytes,
        created_by: str,
        media_type: str | None = None,
        source_uri: str | None = None,
        knowledge_source_grn: str | None = None,
        metadata: dict[str, Any] | None = None,
        labels: dict[str, str] | None = None,
        correlation_id: str | None = None,
        commit: bool = True,
    ) -> Document:
        """Upload a document: normalize, store content, persist the resource.

        Raises:
            UnsupportedDocumentTypeError: extension outside the accepted set.
            NormalizationError: no extraction strategy could read the file.
        """
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_UPLOAD_EXTENSIONS:
            raise UnsupportedDocumentTypeError(
                f"Unsupported document type '{suffix or filename}'. "
                f"Accepted: {', '.join(sorted(SUPPORTED_UPLOAD_EXTENSIONS))}"
            )

        normalized_text = self._normalize_bytes(filename, content)
        content_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
        content_pointer = self.content_store.put_text(
            organization_id=org_id, content=normalized_text
        )
        raw_pointer = self.content_store.put_bytes(
            organization_id=org_id, content=content, suffix=suffix
        )

        grn = GRN(
            org_id=org_id,
            resource_type="document",
            resource_id=str(uuid7()),
            version=1,
        )
        document: Document = self.factory.create(
            "document",
            grn=grn,
            org_id=org_id,
            created_by=created_by,
            filename=filename,
            source_uri=source_uri,
            media_type=media_type,
            content_hash=content_hash,
            byte_size=len(content),
            content_pointer=content_pointer,
            raw_pointer=raw_pointer,
            status=DocumentStatus.UPLOADED,
            knowledge_source_grn=knowledge_source_grn,
            metadata=metadata or {},
            labels=labels or {},
        )
        orm = await self.repo.create(domain_to_orm(document))
        await self.event_repo.append(
            Event(
                type="resource_created",
                principal_id=created_by,
                organization_id=org_id,
                resource_grn=str(grn),
                correlation_id=correlation_id,
                payload={
                    "resource_type": "document",
                    "grn": str(grn),
                    "filename": filename,
                    "media_type": media_type,
                    "content_hash": content_hash,
                    "byte_size": len(content),
                    "knowledge_source_grn": knowledge_source_grn,
                },
                metadata={
                    "service": "DocumentLibraryService",
                    "operation": "upload_document",
                },
            )
        )
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
        return orm_to_domain(orm)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def get_document(self, grn_str: str, org_id: str | None = None) -> Document:
        return orm_to_domain(await self.repo.get_by_grn(grn_str, org_id=org_id))

    async def get_document_text(
        self, grn_str: str, org_id: str | None = None
    ) -> str:
        """Return the normalized text of a document from the content store."""
        document = await self.get_document(grn_str, org_id=org_id)
        if not document.content_pointer:
            return ""
        return self.content_store.read_text(document.content_pointer)

    async def list_documents(
        self,
        org_id: str,
        *,
        status: DocumentStatus | str | None = None,
        knowledge_source_grn: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Document], int]:
        """Paginated org-scoped listing; returns (items, total)."""
        status_value = status.value if isinstance(status, DocumentStatus) else status
        orms, total = await self.repo.list_for_org(
            org_id,
            status=status_value,
            knowledge_source_grn=knowledge_source_grn,
            limit=limit,
            offset=offset,
        )
        return [orm_to_domain(orm) for orm in orms], total

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    async def update_document(
        self,
        grn_str: str,
        *,
        updated_by: str,
        org_id: str | None = None,
        status: DocumentStatus | str | None = None,
        chunk_count: int | None = None,
        knowledge_source_grn: str | None = ...,  # sentinel: unset ≠ None
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        commit: bool = True,
    ) -> Document:
        """Update mutable fields; bumps the resource version."""
        orm = await self.repo.get_by_grn(grn_str, org_id=org_id)
        if status is not None:
            normalized = (
                status if isinstance(status, DocumentStatus) else DocumentStatus(status)
            )
            orm.status = normalized.value
        if chunk_count is not None:
            orm.chunk_count = chunk_count
        if knowledge_source_grn is not ...:
            orm.knowledge_source_grn = knowledge_source_grn
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
                    "resource_type": "document",
                    "grn": grn_str,
                    "status": orm.status,
                    "chunk_count": orm.chunk_count,
                    "knowledge_source_grn": orm.knowledge_source_grn,
                },
                metadata={
                    "service": "DocumentLibraryService",
                    "operation": "update_document",
                },
            )
        )
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
        return orm_to_domain(orm)

    async def delete_document(
        self,
        grn_str: str,
        *,
        deleted_by: str,
        org_id: str | None = None,
        correlation_id: str | None = None,
    ) -> Document:
        """Soft-delete the document row and purge its derived chunks."""
        orm = await self.repo.get_by_grn(grn_str, org_id=org_id)
        orm.state = ResourceState.DELETED
        orm.version += 1
        orm.updated_by = deleted_by
        # Chunks are derived data — hard-delete them with the document.
        await ChunkVectorStore(self.session).delete_for_document(
            grn_str, orm.org_id
        )
        await self.event_repo.append(
            Event(
                type="resource_deleted",
                principal_id=deleted_by,
                organization_id=orm.org_id,
                resource_grn=grn_str,
                correlation_id=correlation_id,
                payload={"resource_type": "document", "grn": grn_str},
                metadata={
                    "service": "DocumentLibraryService",
                    "operation": "delete_document",
                },
            )
        )
        await self.session.commit()
        return orm_to_domain(orm)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _normalize_bytes(self, filename: str, content: bytes) -> str:
        """Materialize bytes to a temp file and run the normalizer."""
        suffix = Path(filename).suffix or ".txt"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        try:
            tmp.write(content)
            tmp.flush()
        finally:
            tmp.close()
        try:
            return self.normalizer.normalize(tmp.name)
        finally:
            self._cleanup_temp_file(Path(tmp.name))

    def _cleanup_temp_file(self, path: Path) -> None:
        """Best-effort cleanup for parser-held temp files (Windows-safe)."""
        for attempt in range(1, _TEMPFILE_UNLINK_RETRIES + 1):
            try:
                path.unlink(missing_ok=True)
                return
            except PermissionError as exc:
                if attempt == _TEMPFILE_UNLINK_RETRIES:
                    logger.warning(
                        "Failed to delete temp file after %s attempts: %s (%s)",
                        _TEMPFILE_UNLINK_RETRIES,
                        path,
                        exc,
                    )
                    return
                time.sleep(_TEMPFILE_UNLINK_BACKOFF_SECONDS * attempt)
