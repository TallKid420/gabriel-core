"""create_resource_projection_table

Revision ID: c5e9f1a2b3d4
Revises: b4d8e9f0c1a2
Create Date: 2026-06-29 23:10:00.000000

Creates resource_projections table for O(1) resource reads and fast listing.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c5e9f1a2b3d4"
down_revision: Union[str, Sequence[str], None] = "b4d8e9f0c1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resource_projections",
        sa.Column("grn", sa.String(length=255), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("attributes", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("last_event_type", sa.String(length=128), nullable=True),
        sa.Column(
            "last_event_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.create_index(
        "ix_resource_projections_organization_id",
        "resource_projections",
        ["organization_id"],
    )
    op.create_index(
        "ix_resource_projections_resource_type",
        "resource_projections",
        ["resource_type"],
    )
    op.create_index(
        "ix_resource_projections_org_type",
        "resource_projections",
        ["organization_id", "resource_type"],
    )
    op.create_index(
        "ix_resource_projections_org_state",
        "resource_projections",
        ["organization_id", "state"],
    )


def downgrade() -> None:
    op.drop_index("ix_resource_projections_org_state", table_name="resource_projections")
    op.drop_index("ix_resource_projections_org_type", table_name="resource_projections")
    op.drop_index("ix_resource_projections_resource_type", table_name="resource_projections")
    op.drop_index("ix_resource_projections_organization_id", table_name="resource_projections")
    op.drop_table("resource_projections")
