"""Document ingestion service (Core).

Orchestrates the Core ingestion pipeline:

    upload bytes / path
        -> normalize to text (DocumentNormalizer)
        -> mint a GRN (via the Universal Resource Model)
        -> build a Document Resource
        -> dispatch a `create_resource` command through the Dispatcher
           (PEEL authorizes it) which records a `resource_created` event
           in the Event Store.

The service is framework-agnostic: it depends only on a Dispatcher and an
ExecutionContext, so it can be driven from the API gateway, a background
worker, or a connector. It contains NO chat / LLM / UI logic.
"""
from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path

from uuid_extensions import uuid7

from gabriel.document.content_store import ContentStore, DiskContentStore
from gabriel.document.models import Document
from gabriel.document.normalizer import DocumentNormalizer
from gabriel.events.command import Command
from gabriel.events.dispatcher import Dispatcher
from gabriel.events.event import Event
from gabriel.resource.grn import GRN
from gabriel.runtime.context import ExecutionContext


@dataclass(frozen=True)
class IngestedDocument:
    """Result of an ingestion: the Document resource and the recorded event."""

    document: Document
    event: Event


class DocumentIngestionService:
    """Ingests documents as first-class Resources and records the fact."""

    def __init__(
        self,
        dispatcher: Dispatcher,
        normalizer: DocumentNormalizer | None = None,
        content_store: ContentStore | None = None,
    ) -> None:
        self.dispatcher = dispatcher
        self.normalizer = normalizer or DocumentNormalizer()
        self.content_store = content_store or DiskContentStore(Path(".gabriel/content"))

    async def ingest(
        self,
        *,
        context: ExecutionContext,
        filename: str,
        content: bytes | None = None,
        path: str | Path | None = None,
        source_uri: str | None = None,
        media_type: str | None = None,
        labels: dict[str, str] | None = None,
        metadata: dict | None = None,
    ) -> IngestedDocument:
        """Ingest a document and emit a `resource_created` event.

        Exactly one of ``content`` or ``path`` must be provided.

        Args:
            context: The execution context (principal + organization).
            filename: Original filename (drives extension-based normalization).
            content: Raw document bytes (mutually exclusive with ``path``).
            path: Path to an existing file (mutually exclusive with ``content``).
            source_uri: Optional origin URI of the document.
            media_type: Optional MIME type.
            labels: Optional resource labels.
            metadata: Optional resource metadata.

        Returns:
            IngestedDocument: the Document resource and the persisted event.
        """
        if (content is None) == (path is None):
            raise ValueError("Provide exactly one of 'content' or 'path'")

        raw_path, byte_size, cleanup = self._materialize(filename, content, path)
        try:
            normalized_text = self.normalizer.normalize(raw_path)
        finally:
            if cleanup:
                Path(raw_path).unlink(missing_ok=True)

        content_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
        content_pointer = self.content_store.put_text(
            organization_id=context.organization,
            content=normalized_text,
        )

        # Mint a GRN within the principal's organization (tenant-scoped).
        resource_id = str(uuid7())
        grn = GRN(
            org_id=context.organization,
            resource_type="document",
            resource_id=resource_id,
            version=1,
        )

        document = Document.create(
            grn=grn,
            org_id=context.organization,
            created_by=str(context.principal.id),
            source_uri=source_uri or (str(path) if path else None),
            media_type=media_type,
            content_hash=content_hash,
            byte_size=byte_size,
            content_pointer=content_pointer,
            labels=labels,
            metadata=metadata,
        )

        # Dispatch through the Dispatcher so PEEL authorizes the action and the
        # Event Store records the ResourceCreated fact transactionally.
        command = Command(
            type="create_resource",
            principal_id=str(context.principal.id),
            organization_id=context.organization,
            action_name="document:create",
            target_resource_grn=str(grn),
            correlation_id=str(context.correlation_id),
            payload={
                "grn": str(grn),
                "resource_type": "document",
                "resource_id": resource_id,
                "version": 1,
                "attributes": {
                    "filename": filename,
                    "media_type": media_type,
                    "source_uri": document.source_uri,
                    "content_hash": content_hash,
                    "content_pointer": content_pointer,
                    "byte_size": byte_size,
                },
            },
            metadata={"execution_id": str(context.execution_id)},
        )

        events = await self.dispatcher.dispatch(command, context)
        return IngestedDocument(document=document, event=events[0])

    # ------------------------------------------------------------------
    @staticmethod
    def _materialize(
        filename: str,
        content: bytes | None,
        path: str | Path | None,
    ) -> tuple[str, int, bool]:
        """Return (path_to_read, byte_size, needs_cleanup)."""
        if path is not None:
            p = Path(path)
            return str(p), p.stat().st_size, False

        assert content is not None
        suffix = Path(filename).suffix or ".txt"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        try:
            tmp.write(content)
            tmp.flush()
        finally:
            tmp.close()
        return tmp.name, len(content), True
