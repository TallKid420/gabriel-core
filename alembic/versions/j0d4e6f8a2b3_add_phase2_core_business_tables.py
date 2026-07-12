"""add conversations, messages, notifications, memory_layer_entries tables

Revision ID: j0d4e6f8a2b3
Revises: i9c3d5e7f1a2
Create Date: 2026-07-12 00:00:00.000000

Implements: Phase 2 — Core Business Logic
            (conversations, messages, agent management, notifications,
            memory layers — see ADR-013)

Changes
-------
1. Create ``conversations`` — org-scoped conversation threads (Universal
   Resources: title, status, participants, optional agent reference).
2. Create ``messages`` — append-only turns within a conversation (role,
   content, token accounting, model used).
3. Create ``notifications`` — per-recipient alerts derived from domain
   events (read/unread state, source event reference).
4. Create ``memory_layer_entries`` — governed memory metadata entries
   (key/value, scope, tags, expiry; key unique per (org, scope, subject)
   namespace). Distinct from the runtime working-memory ``memory_entries``.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "j0d4e6f8a2b3"
down_revision: Union[str, Sequence[str], None] = "i9c3d5e7f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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


def upgrade() -> None:
    # 1. conversations — org-scoped conversation threads
    op.create_table(
        "conversations",
        *_resource_columns(),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, index=True),
        sa.Column("participants", sa.JSON, nullable=False),
        sa.Column("agent_grn", sa.String(255), nullable=True, index=True),
    )
    op.create_index(
        "ix_conversations_org_created", "conversations", ["org_id", "created_at"]
    )

    # 2. messages — append-only turns within a conversation
    op.create_table(
        "messages",
        *_resource_columns(),
        sa.Column("conversation_grn", sa.String(255), nullable=False, index=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("prompt_tokens", sa.Integer, nullable=True),
        sa.Column("completion_tokens", sa.Integer, nullable=True),
        sa.Column("total_tokens", sa.Integer, nullable=True),
        sa.Column("model", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_messages_conversation_created", "messages", ["conversation_grn", "created_at"]
    )

    # 3. notifications — per-recipient alerts derived from domain events
    op.create_table(
        "notifications",
        *_resource_columns(),
        sa.Column("recipient", sa.String(255), nullable=False, index=True),
        sa.Column("type", sa.String(128), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("read", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_event_id", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_notifications_recipient_read", "notifications", ["recipient", "read"]
    )
    op.create_index(
        "ix_notifications_org_recipient_created",
        "notifications",
        ["org_id", "recipient", "created_at"],
    )

    # 4. memory_layer_entries — governed memory metadata entries
    op.create_table(
        "memory_layer_entries",
        *_resource_columns(),
        sa.Column("key", sa.String(255), nullable=False, index=True),
        sa.Column("value", sa.JSON, nullable=True),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("subject_grn", sa.String(255), nullable=True, index=True),
        sa.Column("tags", sa.JSON, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "org_id", "scope", "subject_grn", "key",
            name="uq_memory_layer_entries_namespace_key",
        ),
    )
    op.create_index(
        "ix_memory_layer_entries_org_scope",
        "memory_layer_entries",
        ["org_id", "scope"],
    )


def downgrade() -> None:
    op.drop_table("memory_layer_entries")
    op.drop_table("notifications")
    op.drop_table("messages")
    op.drop_table("conversations")
