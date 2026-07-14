"""Chunk vector store — persistence + similarity search for document chunks.

PostgreSQL: cosine distance via the pgvector ``<=>`` operator (same pattern as
``PostgresMemoryBackend.search``). Other dialects (SQLite in tests): the
candidate rows are loaded and cosine similarity is computed in-process, so the
whole pipeline stays testable without a Postgres instance.

All queries are tenant-scoped: ``org_id`` is always the first filter (P-2).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extensions import uuid7

from gabriel.knowledge.chunk_orm import DocumentChunkORM


def _vector_literal(vec: Sequence[float]) -> str:
    """Render a float list as a pgvector string literal: '[0.1,0.2,...]'."""
    return "[" + ",".join(str(float(x)) for x in vec) + "]"


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Plain cosine similarity; 0.0 when either vector is degenerate."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


@dataclass(frozen=True)
class ChunkSearchResult:
    """One retrieved chunk with its relevance score (higher = closer)."""

    chunk_id: str
    document_grn: str
    knowledge_source_grn: str | None
    chunk_index: int
    content: str
    score: float
    metadata: dict[str, Any]

    def public_view(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_grn": self.document_grn,
            "knowledge_source_grn": self.knowledge_source_grn,
            "chunk_index": self.chunk_index,
            "content": self.content,
            "score": round(self.score, 6),
            "metadata": self.metadata,
        }


class ChunkVectorStore:
    """Persistence and similarity search over ``document_chunks``."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def add_chunk(
        self,
        *,
        org_id: str,
        document_grn: str,
        chunk_index: int,
        content: str,
        token_count: int,
        embedding: list[float] | None = None,
        embedding_model: str | None = None,
        knowledge_source_grn: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DocumentChunkORM:
        """Persist one chunk row (caller controls the transaction)."""
        row = DocumentChunkORM(
            id=str(uuid7()),
            org_id=org_id,
            document_grn=document_grn,
            knowledge_source_grn=knowledge_source_grn,
            chunk_index=chunk_index,
            content=content,
            token_count=token_count,
            embedding=embedding,
            embedding_model=embedding_model,
            chunk_metadata=metadata or {},
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def delete_for_document(self, document_grn: str, org_id: str) -> int:
        """Hard-delete all chunks of a document (tenant-scoped)."""
        result = await self.session.execute(
            delete(DocumentChunkORM).where(
                DocumentChunkORM.org_id == org_id,
                DocumentChunkORM.document_grn == document_grn,
            )
        )
        return int(result.rowcount or 0)

    async def count_for_document(self, document_grn: str, org_id: str) -> int:
        stmt = select(func.count(DocumentChunkORM.id)).where(
            DocumentChunkORM.org_id == org_id,
            DocumentChunkORM.document_grn == document_grn,
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def assign_knowledge_source(
        self,
        document_grn: str,
        org_id: str,
        knowledge_source_grn: str | None,
    ) -> int:
        """Re-label all chunks of a document with a knowledge source GRN."""
        result = await self.session.execute(
            update(DocumentChunkORM)
            .where(
                DocumentChunkORM.org_id == org_id,
                DocumentChunkORM.document_grn == document_grn,
            )
            .values(knowledge_source_grn=knowledge_source_grn)
        )
        return int(result.rowcount or 0)

    async def list_for_document(
        self,
        document_grn: str,
        org_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[DocumentChunkORM], int]:
        """Return (page, total) of a document's chunks in positional order."""
        total = await self.count_for_document(document_grn, org_id)
        stmt = (
            select(DocumentChunkORM)
            .where(
                DocumentChunkORM.org_id == org_id,
                DocumentChunkORM.document_grn == document_grn,
            )
            .order_by(DocumentChunkORM.chunk_index)
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows), total

    # ------------------------------------------------------------------
    # Similarity search
    # ------------------------------------------------------------------

    async def search(
        self,
        *,
        org_id: str,
        query_embedding: list[float],
        knowledge_source_grns: list[str] | None = None,
        document_grns: list[str] | None = None,
        limit: int = 5,
    ) -> list[ChunkSearchResult]:
        """Rank chunks by cosine similarity to *query_embedding*.

        Uses pgvector's ``<=>`` operator on PostgreSQL and an in-process
        cosine fallback on other dialects (e.g. SQLite in tests).
        """
        if self._is_postgres():
            return await self._search_pgvector(
                org_id=org_id,
                query_embedding=query_embedding,
                knowledge_source_grns=knowledge_source_grns,
                document_grns=document_grns,
                limit=limit,
            )
        return await self._search_python(
            org_id=org_id,
            query_embedding=query_embedding,
            knowledge_source_grns=knowledge_source_grns,
            document_grns=document_grns,
            limit=limit,
        )

    async def keyword_search(
        self,
        *,
        org_id: str,
        query: str,
        knowledge_source_grns: list[str] | None = None,
        document_grns: list[str] | None = None,
        limit: int = 5,
    ) -> list[ChunkSearchResult]:
        """Substring fallback when no embedding provider is available."""
        stmt = select(DocumentChunkORM).where(DocumentChunkORM.org_id == org_id)
        if knowledge_source_grns:
            stmt = stmt.where(
                DocumentChunkORM.knowledge_source_grn.in_(knowledge_source_grns)
            )
        if document_grns:
            stmt = stmt.where(DocumentChunkORM.document_grn.in_(document_grns))
        stmt = stmt.where(DocumentChunkORM.content.ilike(f"%{query}%")).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [self._to_result(row, score=0.0) for row in rows]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _is_postgres(self) -> bool:
        bind = self.session.get_bind()
        return bool(bind is not None and bind.dialect.name == "postgresql")

    async def _search_pgvector(
        self,
        *,
        org_id: str,
        query_embedding: list[float],
        knowledge_source_grns: list[str] | None,
        document_grns: list[str] | None,
        limit: int,
    ) -> list[ChunkSearchResult]:
        clauses = ["org_id = :org_id", "embedding IS NOT NULL"]
        params: dict[str, Any] = {
            "org_id": org_id,
            "query_vec": _vector_literal(query_embedding),
            "limit": limit,
        }
        if knowledge_source_grns:
            names = []
            for i, grn in enumerate(knowledge_source_grns):
                key = f"ks_{i}"
                params[key] = grn
                names.append(f":{key}")
            clauses.append(f"knowledge_source_grn IN ({', '.join(names)})")
        if document_grns:
            names = []
            for i, grn in enumerate(document_grns):
                key = f"doc_{i}"
                params[key] = grn
                names.append(f":{key}")
            clauses.append(f"document_grn IN ({', '.join(names)})")

        sql = text(
            f"""
            SELECT id, document_grn, knowledge_source_grn, chunk_index, content,
                   metadata,
                   1 - (embedding <=> :query_vec::vector) AS score
            FROM document_chunks
            WHERE {' AND '.join(clauses)}
            ORDER BY embedding <=> :query_vec::vector
            LIMIT :limit
            """
        )
        rows = (await self.session.execute(sql, params)).mappings().all()
        return [
            ChunkSearchResult(
                chunk_id=row["id"],
                document_grn=row["document_grn"],
                knowledge_source_grn=row["knowledge_source_grn"],
                chunk_index=row["chunk_index"],
                content=row["content"],
                score=float(row["score"]),
                metadata=dict(row["metadata"] or {}),
            )
            for row in rows
        ]

    async def _search_python(
        self,
        *,
        org_id: str,
        query_embedding: list[float],
        knowledge_source_grns: list[str] | None,
        document_grns: list[str] | None,
        limit: int,
    ) -> list[ChunkSearchResult]:
        stmt = select(DocumentChunkORM).where(
            DocumentChunkORM.org_id == org_id,
            DocumentChunkORM.embedding.is_not(None),
        )
        if knowledge_source_grns:
            stmt = stmt.where(
                DocumentChunkORM.knowledge_source_grn.in_(knowledge_source_grns)
            )
        if document_grns:
            stmt = stmt.where(DocumentChunkORM.document_grn.in_(document_grns))

        rows = (await self.session.execute(stmt)).scalars().all()
        scored = sorted(
            (
                (cosine_similarity(query_embedding, row.embedding or []), row)
                for row in rows
            ),
            key=lambda pair: pair[0],
            reverse=True,
        )
        return [self._to_result(row, score=score) for score, row in scored[:limit]]

    @staticmethod
    def _to_result(row: DocumentChunkORM, *, score: float) -> ChunkSearchResult:
        return ChunkSearchResult(
            chunk_id=row.id,
            document_grn=row.document_grn,
            knowledge_source_grn=row.knowledge_source_grn,
            chunk_index=row.chunk_index,
            content=row.content,
            score=score,
            metadata=dict(row.chunk_metadata or {}),
        )
