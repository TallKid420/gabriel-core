"""create_organizations_table

Revision ID: ae642da113fe
Revises: 
Create Date: 2026-06-27 20:45:49.143730

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ae642da113fe'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the organizations table (includes all GabrielResourceMixin columns)."""
    op.create_table(
        "organizations",
        # --- GabrielResourceMixin columns ---
        sa.Column("grn", sa.String(255), primary_key=True, nullable=False),
        sa.Column("org_id", sa.String(128), nullable=False),
        sa.Column(
            "resource_type",
            sa.String(64),
            nullable=False,
        ),
        sa.Column("state", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
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
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("updated_by", sa.String(255), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("labels", sa.JSON(), nullable=False, server_default="{}"),
        # --- Organization-specific columns ---
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(1024), nullable=True),
    )
    op.create_index("ix_organizations_org_id", "organizations", ["org_id"])


def downgrade() -> None:
    """Drop the organizations table."""
    op.drop_index("ix_organizations_org_id", table_name="organizations")
    op.drop_table("organizations")
