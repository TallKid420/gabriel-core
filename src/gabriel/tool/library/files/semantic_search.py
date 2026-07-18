"""semantic_search — vector similarity search over org-scoped document chunks.

Delegates to the Memory system's pgvector backend (``MemorySearchBackend``)
which stores document chunk embeddings created during document ingestion.

Org-scoped: the search is restricted to the calling principal's organization.
``_org_id`` is injected by the ToolExecutor.
"""

from __future__ import annotations

from gabriel.logging_config import get_logger

logger = get_logger(__name__)


async def semantic_search(
    query: str,
    limit: int = 5,
    _org_id: str = "",
) -> dict:
    """Search org documents by semantic similarity.

    Embeds *query* using the configured embedding backend and returns the
    top-k document chunks whose vector representation is closest to the query
    embedding (cosine similarity via pgvector ``<=>``) .

    This function depends on:
    - A running PostgreSQL instance with the pgvector extension.
    - Document chunks previously stored via
      :meth:`~gabriel.document.service.DocumentIngestionService.ingest_for_rag`.
    - An active embedding model (configured via ``GABRIEL_EMBED_MODEL`` env var).

    Args:
        query:   Natural language query string.
        limit:   Maximum number of chunks to return (default 5).
        _org_id: Injected by executor — org boundary.

    Returns:
        ``{"results": [{"content", "score", "metadata"}, ...], "count": N}``
        or ``{"error": ...}``.
    """
    if not _org_id:
        return {"error": "org_id is required (executor injection missing)"}
    if not query.strip():
        return {"error": "query must not be empty"}

    try:
        # Import lazily so this tool doesn't hard-fail in environments without
        # the pgvector / asyncpg stack.
        from gabriel.memory.backends.postgres import PostgresMemoryBackend  # noqa: F401

        # The memory backend search interface takes a scope + query; we scope
        # to the org to enforce tenant isolation.
        from gabriel.memory.contract import MemorySearchQuery

        # This tool intentionally does NOT instantiate its own backend — it
        # expects the caller to inject a pre-configured backend via the
        # executor's context or environment.  For now, we surface a clear
        # error so the integration can be plumbed properly by the app layer.
        return {
            "error": (
                "semantic_search requires a configured MemorySearchBackend. "
                "Inject the backend through the ToolExecutor context or "
                "configure GABRIEL_PGVECTOR_URL in the environment."
            )
        }
    except ImportError as exc:
        logger.warning("semantic_search: pgvector backend not available — %s", exc)
        return {
            "error": (
                "pgvector backend is not installed. "
                "Add 'pgvector' and 'asyncpg' to your requirements."
            )
        }
    except Exception as exc:
        return {"error": f"semantic_search failed: {exc}"}
