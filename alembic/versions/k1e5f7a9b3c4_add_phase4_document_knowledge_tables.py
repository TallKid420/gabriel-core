"""add documents, knowledge_sources, document_chunks tables (pgvector)

Revision ID: k1e5f7a9b3c4
Revises: j0d4e6f8a2b3
Create Date: 2026-07-13 00:00:00.000000

Implements: Phase 4 — Document & Knowledge (see ADR-015)

Changes
-------
1. Create ``documents`` — org-scoped document library rows (Universal
   Resources: filename, content pointers into the disk content store,
   processing status, chunk count, optional knowledge source membership).
2. Create ``knowledge_sources`` — named document collections used as RAG
   grounding for agents (Universal Resources).
3. Create ``document_chunks`` — derived chunk windows of a document's
   normalized text with their embeddings. On PostgreSQL the ``embedding``
   column is pgvector ``vector(768)`` (nomic-embed-text dimensions) with an
   HNSW cosine index; on other dialects (SQLite tests) it stays JSON and
   similarity is computed in-process.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "k1e5f7a9b3c4"
down_revision: Union[str, Sequence[str], None] = "j0d4e6f8a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIMENSIONS = 768  # nomic-embed-text (default Ollama embedding model)


def _resource_columns() -> list[sa.Column]:
    """The GabrielResourceMixin column set shared by all resource tables."""
    return [
        sa.Column("grn", sa.String(255), primary_key=True, nullable=False),
        sa.Column("org_id", sa.String(128), nullable=False, index=True),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("updated_by", sa.String(255), nullable=False),
        sa.Column("metadata", sa.JSON, nullable=False),
        sa.Column("labels", sa.JSON, nullable=False),
    ]


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind is not None and bind.dialect.name == "postgresql"


def upgrade() -> None:
    # 1. documents — org-scoped document library
    op.create_table(
        "documents",
        *_resource_columns(),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("source_uri", sa.String(1000), nullable=True),
        sa.Column("media_type", sa.String(255), nullable=True),
        sa.Column("content_hash", sa.String(128), nullable=True),
        sa.Column("byte_size", sa.Integer, nullable=True),
        sa.Column("content_pointer", sa.String(1000), nullable=True),
        sa.Column("raw_pointer", sa.String(1000), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, index=True),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("knowledge_source_grn", sa.String(255), nullable=True, index=True),
    )
    op.create_index("ix_documents_org_created", "documents", ["org_id", "created_at"])

    # 2. knowledge_sources — document collections for RAG
    op.create_table(
        "knowledge_sources",
        *_resource_columns(),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, index=True),
        sa.Column("document_count", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_knowledge_sources_org_created", "knowledge_sources", ["org_id", "created_at"]
    )

    # 3. document_chunks — derived chunk windows + embeddings
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("org_id", sa.String(128), nullable=False, index=True),
        sa.Column("document_grn", sa.String(255), nullable=False, index=True),
        sa.Column("knowledge_source_grn", sa.String(255), nullable=True, index=True),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("embedding", sa.JSON, nullable=True),
        sa.Column("embedding_model", sa.String(255), nullable=True),
        sa.Column("metadata", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_document_chunks_org_source",
        "document_chunks",
        ["org_id", "knowledge_source_grn"],
    )
    op.create_index(
        "ix_document_chunks_org_document",
        "document_chunks",
        ["org_id", "document_grn"],
    )

    # PostgreSQL: swap the JSON embedding column for a real pgvector column
    # with an HNSW cosine index (ANN search via the ``<=>`` operator).
    if _is_postgres():
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute("ALTER TABLE document_chunks DROP COLUMN embedding")
        op.execute(
            "ALTER TABLE document_chunks "
            f"ADD COLUMN embedding vector({EMBEDDING_DIMENSIONS})"
        )
        op.execute(
            "CREATE INDEX ix_document_chunks_embedding_hnsw "
            "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.drop_index("ix_document_chunks_org_document", table_name="document_chunks")
    op.drop_index("ix_document_chunks_org_source", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index("ix_knowledge_sources_org_created", table_name="knowledge_sources")
    op.drop_table("knowledge_sources")
    op.drop_index("ix_documents_org_created", table_name="documents")
    op.drop_table("documents")
