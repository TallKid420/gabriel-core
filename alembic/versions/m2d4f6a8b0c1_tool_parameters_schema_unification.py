"""tool parameters schema unification

Revision ID: m2d4f6a8b0c1
Revises: l3a7b9c1d5e6
Create Date: 2026-07-19 00:00:00.000000

Unifies the tools table around a single ``parameters`` JSON schema field.

Changes
-------
1. Add ``tools.parameters`` with default empty object.
2. Backfill ``parameters`` from legacy ``input_schema`` values.
3. Narrow ``category`` column length to VARCHAR(64) to match ORM.
4. Drop legacy columns: ``input_schema``, ``output_schema``,
   ``required_capabilities``.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "m2d4f6a8b0c1"
down_revision: Union[str, Sequence[str], None] = "l3a7b9c1d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tools",
        sa.Column(
            "parameters",
            sa.JSON,
            nullable=False,
            server_default="{}",
        ),
    )

    # Preserve existing input contracts while moving to a single field.
    op.execute("UPDATE tools SET parameters = input_schema WHERE input_schema IS NOT NULL")

    with op.batch_alter_table("tools") as batch_op:
        batch_op.alter_column(
            "category",
            existing_type=sa.String(255),
            type_=sa.String(64),
            existing_nullable=False,
        )
        batch_op.drop_column("input_schema")
        batch_op.drop_column("output_schema")
        batch_op.drop_column("required_capabilities")


def downgrade() -> None:
    with op.batch_alter_table("tools") as batch_op:
        batch_op.add_column(
            sa.Column("input_schema", sa.JSON(), nullable=False, server_default="{}")
        )
        batch_op.add_column(
            sa.Column("output_schema", sa.JSON(), nullable=False, server_default="{}")
        )
        batch_op.add_column(
            sa.Column(
                "required_capabilities",
                sa.JSON(),
                nullable=False,
                server_default="[]",
            )
        )
        batch_op.alter_column(
            "category",
            existing_type=sa.String(64),
            type_=sa.String(255),
            existing_nullable=False,
        )

    op.execute("UPDATE tools SET input_schema = parameters WHERE parameters IS NOT NULL")
    op.drop_column("tools", "parameters")
