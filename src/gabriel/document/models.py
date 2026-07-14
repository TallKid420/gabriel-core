"""Document resource model (Core).

In Gabriel Core, a Document IS a Resource. It inherits from the Resource base
class so it participates uniformly in GRN addressing, multi-tenancy, lifecycle,
and PEEL governance — exactly like Agents, Memory, and Files.

Phase 4 (Document & Knowledge) extends the model with library fields
(``filename``, ``status``, ``chunk_count``, ``knowledge_source_grn``,
``raw_pointer``) so documents are durable rows in the ``documents`` table and
can be listed, retrieved, processed into chunks, and grouped into knowledge
sources. All new fields default so pre-existing usage remains valid.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field

from gabriel.resource.grn import GRN
from gabriel.resource.models import Resource, ResourceState, ResourceType


class DocumentStatus(str, Enum):
    """Processing lifecycle of a document, distinct from ResourceState."""

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class Document(Resource):
    """A document that has been ingested into Gabriel.

    Normalized text is stored in a content store. The Resource keeps only a
    pointer and hash metadata. Documents are immutable like all Resources;
    re-ingestion produces a new version.
    """

    resource_type: ResourceType = ResourceType.DOCUMENT

    filename: str = ""
    """Original filename of the upload."""

    source_uri: str | None = None
    """Origin of the document (file path, URL, upload id)."""

    media_type: str | None = None
    """Detected MIME / file type (e.g. 'application/pdf')."""

    content_hash: str | None = None
    """Hash of the normalized content for deduplication / integrity."""

    byte_size: int | None = None
    """Size of the raw uploaded bytes."""

    content_pointer: str | None = None
    """Pointer to normalized content in the backing content store."""

    raw_pointer: str | None = None
    """Pointer to the raw uploaded bytes in the backing content store."""

    status: DocumentStatus = DocumentStatus.UPLOADED
    """Processing status (uploaded → processing → processed | failed)."""

    chunk_count: int = 0
    """Number of chunks produced by the last processing run."""

    knowledge_source_grn: str | None = None
    """GRN of the knowledge source this document belongs to, if any."""

    def public_view(self) -> dict[str, Any]:
        """Serializable representation safe to return from the API."""
        return {
            "grn": str(self.grn),
            "org_id": self.org_id,
            "filename": self.filename,
            "source_uri": self.source_uri,
            "media_type": self.media_type,
            "content_hash": self.content_hash,
            "byte_size": self.byte_size,
            "status": self.status.value,
            "chunk_count": self.chunk_count,
            "knowledge_source_grn": self.knowledge_source_grn,
            "state": self.state.value,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
            "metadata": self.metadata,
            "labels": self.labels,
        }

    @classmethod
    def create(
        cls,
        *,
        grn: GRN,
        org_id: str,
        created_by: str,
        filename: str = "",
        source_uri: str | None = None,
        media_type: str | None = None,
        content_hash: str | None = None,
        byte_size: int | None = None,
        content_pointer: str | None = None,
        raw_pointer: str | None = None,
        status: DocumentStatus = DocumentStatus.UPLOADED,
        knowledge_source_grn: str | None = None,
        labels: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "Document":
        """Mint an ACTIVE Document resource."""
        return cls(
            grn=grn,
            org_id=org_id,
            resource_type=ResourceType.DOCUMENT,
            state=ResourceState.ACTIVE,
            version=grn.version,
            created_by=created_by,
            updated_by=created_by,
            filename=filename,
            source_uri=source_uri,
            media_type=media_type,
            content_hash=content_hash,
            byte_size=byte_size,
            content_pointer=content_pointer,
            raw_pointer=raw_pointer,
            status=status,
            knowledge_source_grn=knowledge_source_grn,
            labels=labels or {},
            metadata=metadata or {},
        )
