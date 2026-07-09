"""PostgreSQL memory backend (ADR-014: Polyglot Memory Fabric).

Implements MemoryAccessInterface against the existing SQLAlchemy
async infrastructure. Extends it with pgvector cosine-similarity
search for the SEMANTIC memory layer (ADR-012, Task 3.2).

Porting notes (from Gabriel/database/)
---------------------------------------
- Embedding generation is delegated to an injected ``embed_fn``
  (matches the pattern from legacy VectorDatabase / OllamaEmbeddings).
- Cosine similarity uses ``<=>`` operator cast: ``embedding::vector <=> ...``
  (exactly as in Gabriel/db/repositories.py::VectorRepository.search).
- All queries are tenant-scoped: ``org_id`` is the first WHERE clause.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, List, Optional

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gabriel.memory.contract import MemoryAccessInterface
from gabriel.memory.models import MemoryEntry, MemoryLayer
from gabriel.memory.orm import MemoryEntryORM


# Embed function signature: takes a string, returns a float list (can be async).
EmbedFn = Callable[[str], Awaitable[List[float]]]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _vector_literal(vec: List[float]) -> str:
    """Render float list as pgvector string literal: '[0.1,0.2,...]'."""
    return "[" + ",".join(str(float(x)) for x in vec) + "]"


def _orm_to_entry(row: MemoryEntryORM) -> MemoryEntry:
    """Map ORM row → domain MemoryEntry."""
    meta: dict[str, Any] = dict(row.entry_metadata or {})
    # Expose the ORM id so callers can use it with forget()
    meta.setdefault("_id", row.id)
    meta.setdefault("_org_id", row.org_id)
    meta.setdefault("_agent_id", row.agent_id)
    meta.setdefault("_scope", row.scope)
    meta.setdefault("_created_at", row.created_at.isoformat() if row.created_at else None)
    return MemoryEntry(
        layer=MemoryLayer(row.layer),
        content=row.content,
        importance=row.importance,
        metadata=meta,
    )


class PostgresMemoryBackend(MemoryAccessInterface):
    """Durable PostgreSQL memory backend with optional pgvector semantic search.

    Parameters
    ----------
    session_factory:
        The async_sessionmaker from ``gabriel.database.session``.
    org_id:
        The organisation this backend is scoped to. All reads and writes
        are filtered to this tenant — cross-org access is structurally
        impossible (P-2).
    agent_id:
        Optional agent scope. When set, queries are further narrowed to
        entries from this agent.
    embed_fn:
        Async callable ``(text) -> list[float]`` used to embed content
        before storage and queries before search. Required for semantic
        search; ``search()`` raises ``RuntimeError`` if not provided.
    scope:
        Default scope label stored on new entries (default ``"agent"``).
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        org_id: str,
        agent_id: Optional[str] = None,
        embed_fn: Optional[EmbedFn] = None,
        scope: str = "agent",
    ) -> None:
        self._sessions = session_factory
        self._org_id = org_id
        self._agent_id = agent_id
        self._embed_fn = embed_fn
        self._scope = scope

    # ------------------------------------------------------------------
    # MAI implementation
    # ------------------------------------------------------------------

    async def store(self, entry: MemoryEntry) -> str:
        """Persist a MemoryEntry to PostgreSQL.

        For SEMANTIC layer entries, generates an embedding via ``embed_fn``
        and stores it in the ``embedding`` column (pgvector compatible).
        """
        from uuid_extensions import uuid7

        entry_id = str(uuid7())

        # Generate embedding for semantic entries if embed_fn is available
        embedding: Optional[List[float]] = None
        if entry.layer == MemoryLayer.SEMANTIC and self._embed_fn is not None:
            embedding = await self._embed_fn(str(entry.content))

        orm_row = MemoryEntryORM(
            id=entry_id,
            org_id=self._org_id,
            agent_id=self._agent_id,
            layer=entry.layer.value,
            scope=self._scope,
            content=str(entry.content),
            importance=entry.importance,
            embedding=embedding,
            entry_metadata={
                **entry.metadata,
                "_principal": entry.metadata.get("principal"),
            },
        )

        async with self._sessions() as session:
            session.add(orm_row)
            await session.commit()

        return entry_id

    async def retrieve(
        self,
        layer: MemoryLayer,
        query: Optional[str] = None,
        limit: int = 10,
    ) -> List[MemoryEntry]:
        """Fetch entries from a layer with optional keyword filter.

        Always scoped to ``org_id`` (and ``agent_id`` when set).
        """
        async with self._sessions() as session:
            stmt = (
                select(MemoryEntryORM)
                .where(
                    MemoryEntryORM.org_id == self._org_id,
                    MemoryEntryORM.layer == layer.value,
                )
                .order_by(MemoryEntryORM.created_at.desc())
                .limit(limit)
            )

            if self._agent_id is not None:
                stmt = stmt.where(MemoryEntryORM.agent_id == self._agent_id)

            # Simple substring filter (for non-semantic layers)
            if query is not None:
                stmt = stmt.where(MemoryEntryORM.content.ilike(f"%{query}%"))

            result = await session.execute(stmt)
            rows = result.scalars().all()

        return [_orm_to_entry(r) for r in rows]

    async def search(
        self,
        query: str,
        layer: Optional[MemoryLayer] = None,
        limit: int = 10,
    ) -> List[MemoryEntry]:
        """Semantic search using pgvector cosine distance (``<=>``).

        Ranks memory entries by relevance to *query*. Requires ``embed_fn``
        to be set; falls back to keyword :meth:`retrieve` otherwise.

        Ported from: Gabriel/db/repositories.py::VectorRepository.search
        """
        if self._embed_fn is None:
            # Graceful degradation — no embedder wired in
            target_layer = layer or MemoryLayer.SEMANTIC
            return await self.retrieve(layer=target_layer, query=query, limit=limit)

        query_vec = await self._embed_fn(query)
        vec_str = _vector_literal(query_vec)

        # Build raw SQL for cosine similarity — pgvector <=> operator
        # We cast the stored JSON array and the query literal to ::vector
        layer_clause = ""
        if layer is not None:
            layer_clause = f"AND layer = '{layer.value}'"

        agent_clause = ""
        if self._agent_id is not None:
            agent_clause = f"AND agent_id = '{self._agent_id}'"

        sql = text(
            f"""
            SELECT id, org_id, agent_id, layer, scope, content,
                   importance, metadata, embedding, created_at, expires_at
            FROM memory_entries
            WHERE org_id = :org_id
              {layer_clause}
              {agent_clause}
              AND embedding IS NOT NULL
            ORDER BY embedding::vector <=> :query_vec::vector
            LIMIT :limit
            """
        )

        async with self._sessions() as session:
            result = await session.execute(
                sql,
                {"org_id": self._org_id, "query_vec": vec_str, "limit": limit},
            )
            rows = result.mappings().all()

        entries: List[MemoryEntry] = []
        for row in rows:
            meta = dict(row["metadata"] or {})
            meta.setdefault("_id", row["id"])
            meta.setdefault("_org_id", row["org_id"])
            meta.setdefault("_scope", row["scope"])
            entries.append(
                MemoryEntry(
                    layer=MemoryLayer(row["layer"]),
                    content=row["content"],
                    importance=row["importance"],
                    metadata=meta,
                )
            )
        return entries

    async def forget(self, memory_id: str) -> None:
        """Hard-delete a single memory entry by ID.

        Scoped to org_id — cannot delete entries belonging to another tenant.
        """
        async with self._sessions() as session:
            stmt = delete(MemoryEntryORM).where(
                MemoryEntryORM.id == memory_id,
                MemoryEntryORM.org_id == self._org_id,  # tenant isolation
            )
            await session.execute(stmt)
            await session.commit()
