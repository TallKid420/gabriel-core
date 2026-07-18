"""Document processing pipeline (Phase 4 — Document & Knowledge).

Turns an uploaded document into retrievable chunks:

    normalized text (content store)
        -> TextChunker (configurable size/overlap)
        -> EmbeddingProvider (Ollama by default; hot-swappable)
        -> ChunkVectorStore rows (pgvector on PostgreSQL)

Embedding failures degrade gracefully: chunks are stored WITHOUT embeddings
(keyword search still works) and the document is marked ``processed`` with
``embedded=False`` recorded in its metadata, so a later re-process can fill
the vectors in once the embedding backend is reachable.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from gabriel.document.library import DocumentLibraryService
from gabriel.document.models import Document, DocumentStatus
from gabriel.logging_config import get_logger
from gabriel.knowledge.chunking import TextChunker
from gabriel.knowledge.embeddings import EmbeddingError, EmbeddingProvider
from gabriel.knowledge.vector_store import ChunkVectorStore

logger = get_logger(__name__)

EMBED_BATCH_SIZE = 32


@dataclass(frozen=True)
class ProcessingResult:
    """Outcome of one processing run."""

    document: Document
    chunk_count: int
    embedded: bool
    embedding_model: str | None


class DocumentProcessingService:
    """Chunk + embed a document's normalized text into the vector store."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        library: DocumentLibraryService | None = None,
        chunker: TextChunker | None = None,
        embedder: EmbeddingProvider | None = None,
    ):
        self.session = session
        self.library = library or DocumentLibraryService(session)
        self.chunker = chunker or TextChunker()
        self.embedder = embedder
        self.chunks = ChunkVectorStore(session)

    async def process_document(
        self,
        grn_str: str,
        *,
        org_id: str,
        processed_by: str,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        correlation_id: str | None = None,
    ) -> ProcessingResult:
        """(Re-)process a document: replace its chunks and update status."""
        document = await self.library.get_document(grn_str, org_id=org_id)
        text = await self.library.get_document_text(grn_str, org_id=org_id)

        chunker = self.chunker
        if chunk_size is not None or chunk_overlap is not None:
            chunker = TextChunker(
                chunk_size=chunk_size or self.chunker.chunk_size,
                chunk_overlap=(
                    chunk_overlap
                    if chunk_overlap is not None
                    else self.chunker.chunk_overlap
                ),
            )
        chunks = chunker.split(text)

        # Embed in batches; degrade to un-embedded chunks on failure.
        embeddings: list[list[float] | None] = [None] * len(chunks)
        embedded = False
        embedding_model: str | None = None
        if self.embedder is not None and chunks:
            try:
                collected: list[list[float]] = []
                texts = [chunk.text for chunk in chunks]
                for start in range(0, len(texts), EMBED_BATCH_SIZE):
                    collected.extend(
                        await self.embedder.embed(texts[start : start + EMBED_BATCH_SIZE])
                    )
                embeddings = list(collected)
                embedded = True
                embedding_model = self.embedder.model
            except EmbeddingError as exc:
                logger.warning(
                    "Embedding unavailable for %s (%s); storing chunks without "
                    "vectors — keyword search only until re-processed.",
                    grn_str,
                    exc,
                )

        # Replace chunks atomically within the service transaction.
        await self.chunks.delete_for_document(grn_str, org_id)
        for chunk, vector in zip(chunks, embeddings):
            await self.chunks.add_chunk(
                org_id=org_id,
                document_grn=grn_str,
                knowledge_source_grn=document.knowledge_source_grn,
                chunk_index=chunk.index,
                content=chunk.text,
                token_count=chunk.token_count,
                embedding=vector,
                embedding_model=embedding_model if vector is not None else None,
                metadata={
                    "filename": document.filename,
                    "chunk_total": len(chunks),
                    "chunk_size": chunker.chunk_size,
                    "chunk_overlap": chunker.chunk_overlap,
                },
            )

        updated = await self.library.update_document(
            grn_str,
            updated_by=processed_by,
            org_id=org_id,
            status=DocumentStatus.PROCESSED,
            chunk_count=len(chunks),
            metadata={
                "embedded": embedded,
                "embedding_model": embedding_model,
                "chunk_size": chunker.chunk_size,
                "chunk_overlap": chunker.chunk_overlap,
            },
            correlation_id=correlation_id,
        )
        return ProcessingResult(
            document=updated,
            chunk_count=len(chunks),
            embedded=embedded,
            embedding_model=embedding_model,
        )
