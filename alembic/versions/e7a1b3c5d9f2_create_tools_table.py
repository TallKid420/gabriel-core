"""create_tools_table

Revision ID: e7a1b3c5d9f2
Revises: d6f0a2b4c8e1
Create Date: 2026-07-06 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7a1b3c5d9f2"
down_revision: Union[str, Sequence[str], None] = "d6f0a2b4c8e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tools",
        sa.Column("grn", sa.String(255), primary_key=True, nullable=False),
        sa.Column("org_id", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
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
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(1024), nullable=False),
        sa.Column("category", sa.String(255), nullable=False),
        sa.Column("input_schema", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("output_schema", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("safety_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("required_capabilities", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_tools_org_id", "tools", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_tools_org_id", table_name="tools")
    op.drop_table("tools")
