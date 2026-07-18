"""RAG retrieval — turn a user query into gateway context blocks.

The ``KnowledgeRetriever`` is the bridge between the knowledge slice and the
gateway runtime: given a query it embeds the text, runs a cosine-similarity
search over ``document_chunks`` (scoped to the agent's knowledge sources),
and packages the winning chunks as ``ContextBlock``s that the Phase 3
``PromptAssembler`` injects into the system prompt.

Degradation, not failure (P-1 self-healing): if the embedding provider is
unreachable the retriever falls back to keyword search, and any unexpected
error yields an empty result — a chat turn must never break because RAG did.
"""
from __future__ import annotations

from typing import Callable

from gabriel.gateway.prompt import ContextBlock
from gabriel.logging_config import get_logger
from gabriel.knowledge.embeddings import (
    EmbeddingError,
    EmbeddingProvider,
    EmbeddingProviderRegistry,
)
from gabriel.knowledge.vector_store import ChunkSearchResult, ChunkVectorStore

logger = get_logger("gabriel.knowledge.retrieval")

DEFAULT_RETRIEVAL_LIMIT = 4
DEFAULT_MAX_CONTEXT_CHARS = 2000


class KnowledgeRetriever:
    """Retrieves relevant document chunks for a query, org-scoped."""

    def __init__(
        self,
        session_factory: Callable,
        embedder: EmbeddingProvider | None = None,
        *,
        registry: EmbeddingProviderRegistry | None = None,
    ):
        self.session_factory = session_factory
        self._embedder = embedder
        self._registry = registry

    def _resolve_embedder(self) -> EmbeddingProvider | None:
        if self._embedder is not None:
            return self._embedder
        if self._registry is not None:
            try:
                return self._registry.resolve()
            except Exception:  # noqa: BLE001 - registry may be empty
                return None
        return None

    # ------------------------------------------------------------------

    async def search_chunks(
        self,
        *,
        org_id: str,
        query: str,
        knowledge_source_grns: list[str] | None = None,
        document_grns: list[str] | None = None,
        limit: int = DEFAULT_RETRIEVAL_LIMIT,
    ) -> list[ChunkSearchResult]:
        """Similarity search with keyword fallback; returns raw results."""
        embedder = self._resolve_embedder()
        async with self.session_factory() as session:
            store = ChunkVectorStore(session)
            if embedder is not None:
                try:
                    vectors = await embedder.embed([query])
                    return await store.search(
                        org_id=org_id,
                        query_embedding=vectors[0],
                        knowledge_source_grns=knowledge_source_grns,
                        document_grns=document_grns,
                        limit=limit,
                    )
                except EmbeddingError as exc:
                    logger.warning(
                        "embedding failed (%s); falling back to keyword search", exc
                    )
            return await store.keyword_search(
                org_id=org_id,
                query=query,
                knowledge_source_grns=knowledge_source_grns,
                document_grns=document_grns,
                limit=limit,
            )

    async def retrieve(
        self,
        *,
        org_id: str,
        query: str,
        knowledge_source_grns: list[str] | None = None,
        document_grns: list[str] | None = None,
        limit: int = DEFAULT_RETRIEVAL_LIMIT,
        max_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
    ) -> list[ContextBlock]:
        """Retrieve chunks and package them as prompt context blocks.

        Never raises: retrieval problems are logged and produce an empty
        list so the chat turn proceeds without grounding.
        """
        try:
            results = await self.search_chunks(
                org_id=org_id,
                query=query,
                knowledge_source_grns=knowledge_source_grns,
                document_grns=document_grns,
                limit=limit,
            )
        except Exception:  # noqa: BLE001 - RAG must never break a turn
            logger.exception("knowledge retrieval failed; continuing without context")
            return []

        blocks: list[ContextBlock] = []
        used = 0
        for result in results:
            content = result.content.strip()
            if not content:
                continue
            if used + len(content) > max_chars and blocks:
                break
            content = content[: max(0, max_chars - used)]
            filename = (result.metadata or {}).get("filename")
            label = filename or result.document_grn
            blocks.append(
                ContextBlock(
                    source=f"knowledge:{label}#chunk{result.chunk_index}",
                    content=content,
                )
            )
            used += len(content)
        return blocks
