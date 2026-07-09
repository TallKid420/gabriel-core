"""Phase 2 Tool Migration — add runtime_binding to tools + external_integrations table.

Revision ID: h2b4c6d8e0f1
Revises: g8b1c2d3e4f5
Create Date: 2026-07-07 00:00:00.000000

Changes
-------
1. tools table:
   - ADD COLUMN runtime_binding VARCHAR(255) NOT NULL DEFAULT ''

2. external_integrations table (new):
   Stores org-scoped OAuth credentials / IMAP-SMTP configs for
   third-party integrations (Gmail, Google Calendar, etc.)

   Columns follow the GabrielResourceMixin pattern so PEEL can
   enforce org-level access via grn + org_id.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "h2b4c6d8e0f1"
down_revision: Union[str, Sequence[str], None] = "g8b1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Add runtime_binding to the existing tools table
    # ------------------------------------------------------------------
    op.add_column(
        "tools",
        sa.Column(
            "runtime_binding",
            sa.String(255),
            nullable=False,
            server_default="",
        ),
    )

    # ------------------------------------------------------------------
    # 2. Create external_integrations table
    # ------------------------------------------------------------------
    op.create_table(
        "external_integrations",
        # --- GabrielResourceMixin columns ---
        sa.Column("grn", sa.String(255), primary_key=True, nullable=False),
        sa.Column("org_id", sa.String(128), nullable=False, index=True),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column(
            "state",
            sa.String(32),
            nullable=False,
            server_default="active",
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("updated_by", sa.String(255), nullable=False),
        sa.Column("resource_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("labels", sa.JSON(), nullable=False, server_default="{}"),
        # --- ExternalIntegration-specific columns ---
        # Type slug, e.g. "gmail", "google_calendar", "imap_smtp"
        sa.Column("integration_type", sa.String(64), nullable=False),
        # Display name for the integration (e.g. "Work Gmail")
        sa.Column("display_name", sa.String(255), nullable=False, server_default=""),
        # JSON blob: OAuth tokens, IMAP/SMTP creds — stored as-is.
        # Production deployments MUST encrypt this column at rest.
        sa.Column("credentials", sa.JSON(), nullable=False, server_default="{}"),
        # Comma-separated OAuth scopes granted, e.g. "gmail.send,gmail.readonly"
        sa.Column("scopes", sa.String(1024), nullable=False, server_default=""),
        # Whether credentials are still valid / connected
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_table("external_integrations")
    op.drop_column("tools", "runtime_binding")
