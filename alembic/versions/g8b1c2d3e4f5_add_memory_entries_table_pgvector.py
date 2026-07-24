"""add_memory_entries_table_pgvector

Revision ID: g8b1c2d3e4f5
Revises: f174bb2bb84c
Create Date: 2026-07-07 00:00:00.000000

Implements: ADR-012 (Multi-Layer Memory), ADR-014 (Polyglot Memory Fabric),
            Task 3.1 (PostgreSQL Memory Backend), Task 3.2 (pgvector Semantic Search)

Changes
-------
1. Enable the ``pgvector`` extension (CREATE EXTENSION IF NOT EXISTS vector).
2. Create the ``memory_entries`` table with all required columns.
3. Add the ``embedding`` column as ``vector(1536)`` for cosine similarity search.
4. Create indexes for tenant-scoped and agent-scoped queries.
5. Create an HNSW index on the embedding column for efficient ANN search.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "g8b1c2d3e4f5"
down_revision: Union[str, Sequence[str], None] = "f174bb2bb84c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Detect dialect to handle SQLite vs PostgreSQL differences
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == "postgresql"
    
    # 1. Enable pgvector extension (PostgreSQL only)
    if is_postgresql:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. Create memory_entries table
    op.create_table(
        "memory_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(128), nullable=False),
        sa.Column("agent_id", sa.String(255), nullable=True),
        sa.Column("layer", sa.String(64), nullable=False),
        sa.Column("scope", sa.String(64), nullable=False, server_default="agent"),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("importance", sa.Float, nullable=False, server_default="1.0"),
        # embedding declared as JSONB initially; ALTER below converts to vector(1536)
        sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()") if is_postgresql else sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 3. Add embedding column as pgvector type (PostgreSQL) or JSON fallback (SQLite)
    #    Using raw DDL because SQLAlchemy doesn't know the vector type without pgvector lib.
    if is_postgresql:
        op.execute(
            "ALTER TABLE memory_entries ADD COLUMN embedding vector(1536)"
        )
    else:
        # SQLite: store embedding as JSON array (no vector similarity index support)
        op.execute(
            "ALTER TABLE memory_entries ADD COLUMN embedding TEXT"
        )

    # 4. Standard indexes for tenant-scoped lookups
    op.create_index("ix_memory_entries_org_id", "memory_entries", ["org_id"])
    op.create_index("ix_memory_entries_agent_id", "memory_entries", ["agent_id"])
    op.create_index("ix_memory_entries_org_layer", "memory_entries", ["org_id", "layer"])
    op.create_index(
        "ix_memory_entries_agent_layer", "memory_entries", ["agent_id", "layer"]
    )

    # 5. HNSW index for approximate nearest-neighbor search on the embedding column (PostgreSQL only).
    #    ivfflat is also valid; HNSW has better recall and no training step.
    if is_postgresql:
        op.execute(
            """
            CREATE INDEX ix_memory_entries_embedding_hnsw
            ON memory_entries
            USING hnsw (embedding vector_cosine_ops)
            """
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_memory_entries_embedding_hnsw")
    op.drop_index("ix_memory_entries_agent_layer", table_name="memory_entries")
    op.drop_index("ix_memory_entries_org_layer", table_name="memory_entries")
    op.drop_index("ix_memory_entries_agent_id", table_name="memory_entries")
    op.drop_index("ix_memory_entries_org_id", table_name="memory_entries")
    op.drop_table("memory_entries")
    # Do not drop the vector extension — other tables may use it.
