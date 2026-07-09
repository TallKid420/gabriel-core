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
from gabriel.memory.contract import MemoryAccessInterface
from gabriel.memory.models import MemoryEntry, MemoryLayer
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
    # Task 3.4: Document chunking for RAG
    # ------------------------------------------------------------------

    async def ingest_for_rag(
        self,
        *,
        context: ExecutionContext,
        filename: str,
        content: bytes | None = None,
        path: str | Path | None = None,
        memory_backend: "MemoryAccessInterface | None" = None,
        source_uri: str | None = None,
        media_type: str | None = None,
        labels: dict[str, str] | None = None,
        metadata: dict | None = None,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
    ) -> "IngestedDocument":
        """Ingest a document AND store its chunks as SEMANTIC memory entries.

        Extends the base :meth:`ingest` pipeline with a chunking + embedding
        step so documents become searchable via the memory system (RAG).

        Chunking strategy (ported from Gabriel/daemon/database.py):
        - Tokenise by whitespace (1 token ≈ 1 word).
        - Fixed-size windows of *chunk_size* tokens with *chunk_overlap* overlap.
        - Each chunk is stored as a SEMANTIC MemoryEntry via *memory_backend*.

        Args:
            context        : Execution context (principal + org).
            filename       : Original filename for normalisation.
            content        : Raw bytes (mutually exclusive with *path*).
            path           : Existing file path (mutually exclusive with *content*).
            memory_backend : A MemoryAccessInterface backend to store chunks in.
                             If ``None``, chunking is skipped (falls back to
                             plain :meth:`ingest`).
            source_uri     : Optional origin URI attached to metadata.
            media_type     : Optional MIME type.
            labels         : Optional resource labels.
            metadata       : Optional resource metadata.
            chunk_size     : Token window size (default 512).
            chunk_overlap  : Overlap between consecutive windows (default 64).

        Returns:
            IngestedDocument: The Document resource and the persisted event.
            Chunks are stored as side effects in the memory backend.
        """
        # 1. Normalise text upfront so we can chunk without re-reading the store
        raw_path, _byte_size, cleanup = self._materialize(filename, content, path)
        try:
            normalized_text = self.normalizer.normalize(raw_path)
        finally:
            if cleanup:
                Path(raw_path).unlink(missing_ok=True)

        # 2. Standard ingestion (GRN, event store, content store).
        #    Pass the already-normalised bytes so DocumentNormalizer re-uses
        #    them rather than re-reading from disk.
        result = await self.ingest(
            context=context,
            filename=filename,
            content=normalized_text.encode("utf-8") if content is not None else None,
            path=path if content is None else None,
            source_uri=source_uri,
            media_type=media_type,
            labels=labels,
            metadata=metadata,
        )

        if memory_backend is None:
            return result

        # 3. Chunk the text into token windows with overlap
        chunks = self._chunk_tokens(normalized_text, chunk_size, chunk_overlap)

        # 4. Store each chunk as a SEMANTIC memory entry
        doc_grn = str(result.document.grn)
        for idx, chunk in enumerate(chunks):
            entry = MemoryEntry(
                layer=MemoryLayer.SEMANTIC,
                content=chunk,
                importance=1.0,
                metadata={
                    "source_grn": doc_grn,
                    "source_uri": source_uri or filename,
                    "chunk_index": idx,
                    "chunk_total": len(chunks),
                    "org": context.organization,
                    "principal": str(context.principal.id),
                },
            )
            await memory_backend.store(entry)

        return result

    @staticmethod
    def _chunk_tokens(
        text: str,
        chunk_size: int = 512,
        overlap: int = 64,
    ) -> list[str]:
        """Split text into overlapping token windows.

        A 'token' is a whitespace-delimited word — consistent with the
        512-token / 64-token overlap spec and the chunking approach in
        Gabriel/daemon/database.py::VectorDatabase.chunk_text.

        Args:
            text       : Plain text to chunk.
            chunk_size : Window size in tokens.
            overlap    : Number of tokens shared between consecutive windows.

        Returns:
            List of chunk strings.
        """
        tokens = text.split()
        if not tokens:
            return []

        step = max(1, chunk_size - overlap)
        chunks: list[str] = []
        start = 0
        while start < len(tokens):
            end = min(start + chunk_size, len(tokens))
            chunks.append(" ".join(tokens[start:end]))
            if end == len(tokens):
                break
            start += step
        return chunks

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
