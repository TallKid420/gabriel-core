"""create_principals_and_events_tables

Revision ID: b4d8e9f0c1a2
Revises: ae642da113fe
Create Date: 2026-06-29 22:00:00.000000

Creates:
- principals table (identity abstractions, keyed by PrincipalID)
- events table (append-only event log for ADR-017 transactional outbox)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4d8e9f0c1a2'
down_revision: Union[str, Sequence[str], None] = 'ae642da113fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create principals and events tables."""
    
    # Create principals table (identity abstractions)
    op.create_table(
        "principals",
        # PK: principal_id (PrincipalID as string)
        sa.Column("principal_id", sa.String(225), primary_key=True, nullable=False),
        # FK: org_id -> organizations.org_id (tenant isolation)
        sa.Column(
            "org_id",
            sa.String(128),
            sa.ForeignKey("organizations.org_id"),
            nullable=False,
            index=True,
        ),
        # Principal metadata
        sa.Column("principal_type", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        # Capabilities and mirroring
        sa.Column("capabilities", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("resource_grn", sa.String(225), nullable=True),
        # Metadata
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_principals_org_id", "principals", ["org_id"])
    
    # Create events table (append-only event log, ADR-017)
    op.create_table(
        "events",
        # PK: event id (UUID)
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        # Tenant isolation
        sa.Column("organization_id", sa.String(128), nullable=False, index=True),
        # Event metadata
        sa.Column("type", sa.String(128), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            index=True,
        ),
        # Resource reference (nullable for org-level events)
        sa.Column("resource_grn", sa.String(255), nullable=True, index=True),
        # Principal who triggered
        sa.Column("principal_id", sa.String(255), nullable=False),
        # Tracing
        sa.Column("correlation_id", sa.String(36), nullable=True, index=True),
        sa.Column("causation_id", sa.String(36), nullable=True),
        # Extensible data
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("meta", sa.JSON(), nullable=False, server_default="{}"),
    )
    # Composite indexes for efficient querying
    op.create_index(
        "ix_events_org_occurred",
        "events",
        ["organization_id", "occurred_at"],
    )
    op.create_index(
        "ix_events_resource_occurred",
        "events",
        ["resource_grn", "occurred_at"],
    )


def downgrade() -> None:
    """Drop principals and events tables."""
    # Drop events table
    op.drop_index("ix_events_resource_occurred", table_name="events")
    op.drop_index("ix_events_org_occurred", table_name="events")
    op.drop_table("events")
    
    # Drop principals table
    op.drop_index("ix_principals_org_id", table_name="principals")
    op.drop_table("principals")
