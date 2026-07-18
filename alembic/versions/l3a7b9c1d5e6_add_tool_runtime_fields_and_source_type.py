"""add tool runtime/enabled/configuration columns and knowledge source_type

Revision ID: l3a7b9c1d5e6
Revises: k1e5f7a9b3c4
Create Date: 2026-07-16 00:00:00.000000

Implements: V1 Tool & Knowledge resource model extensions (ADR-009 / ADR-016)

Changes
-------
1. ``tools.execution_runtime`` — declared execution topology for the tool
   (``local`` / ``enterprise`` / ``cloud`` / ``edge``). V1 declaration only;
   no routing engine consumes it yet.
2. ``tools.enabled`` — org-level enable/disable flag honoured by the chat
   runtime when resolving an agent's allowed tools.
3. ``tools.configuration`` — per-tool configuration payload (JSON).
4. ``knowledge_sources.source_type`` — kind of knowledge source
   (``vector_collection`` / ``document_collection`` / ``external``),
   decoupling the knowledge abstraction from the vector store.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "l3a7b9c1d5e6"
down_revision: Union[str, Sequence[str], None] = "k1e5f7a9b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tools",
        sa.Column(
            "execution_runtime",
            sa.String(32),
            nullable=False,
            server_default="local",
        ),
    )
    op.add_column(
        "tools",
        sa.Column(
            "enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "tools",
        sa.Column(
            "configuration",
            sa.JSON,
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "knowledge_sources",
        sa.Column(
            "source_type",
            sa.String(32),
            nullable=False,
            server_default="vector_collection",
        ),
    )
    op.create_index(
        "ix_knowledge_sources_source_type",
        "knowledge_sources",
        ["source_type"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_sources_source_type", table_name="knowledge_sources"
    )
    op.drop_column("knowledge_sources", "source_type")
    op.drop_column("tools", "configuration")
    op.drop_column("tools", "enabled")
    op.drop_column("tools", "execution_runtime")
