"""Document resource model (Core).

In Gabriel Core, a Document IS a Resource. It inherits from the Resource base
class so it participates uniformly in GRN addressing, multi-tenancy, lifecycle,
and PEEL governance — exactly like Agents, Memory, and Files.
"""
from __future__ import annotations

from typing import Any

from pydantic import Field

from gabriel.resource.grn import GRN
from gabriel.resource.models import Resource, ResourceState, ResourceType


class Document(Resource):
    """A document that has been ingested into Gabriel.

    The normalized text is referenced by content (or a content pointer in
    metadata for large blobs). Documents are immutable like all Resources;
    re-ingestion produces a new version.
    """

    resource_type: ResourceType = ResourceType.DOCUMENT

    source_uri: str | None = None
    """Origin of the document (file path, URL, upload id)."""

    media_type: str | None = None
    """Detected MIME / file type (e.g. 'application/pdf')."""

    content_hash: str | None = None
    """Hash of the normalized content for deduplication / integrity."""

    byte_size: int | None = None
    """Size of the raw uploaded bytes."""

    normalized_text: str | None = None
    """Normalized Markdown/plain-text content extracted at ingestion."""

    @classmethod
    def create(
        cls,
        *,
        grn: GRN,
        org_id: str,
        created_by: str,
        source_uri: str | None = None,
        media_type: str | None = None,
        content_hash: str | None = None,
        byte_size: int | None = None,
        normalized_text: str | None = None,
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
            source_uri=source_uri,
            media_type=media_type,
            content_hash=content_hash,
            byte_size=byte_size,
            normalized_text=normalized_text,
            labels=labels or {},
            metadata=metadata or {},
        )
