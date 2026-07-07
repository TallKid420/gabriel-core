"""create_audit_log_table

Revision ID: a1c9e4d7f2b3
Revises: f174bb2bb84c
Create Date: 2026-07-07 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1c9e4d7f2b3"
down_revision: Union[str, Sequence[str], None] = "f174bb2bb84c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.String(length=128), nullable=False),
        sa.Column("principal_id", sa.String(length=255), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=True),
        sa.Column("resource_grn", sa.String(length=255), nullable=True),
        sa.Column("correlation_id", sa.String(length=36), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(op.f("ix_audit_log_action"), "audit_log", ["action"], unique=False)
    op.create_index(op.f("ix_audit_log_correlation_id"), "audit_log", ["correlation_id"], unique=False)
    op.create_index(op.f("ix_audit_log_decision"), "audit_log", ["decision"], unique=False)
    op.create_index(op.f("ix_audit_log_event_type"), "audit_log", ["event_type"], unique=False)
    op.create_index(op.f("ix_audit_log_occurred_at"), "audit_log", ["occurred_at"], unique=False)
    op.create_index(op.f("ix_audit_log_organization_id"), "audit_log", ["organization_id"], unique=False)
    op.create_index(op.f("ix_audit_log_principal_id"), "audit_log", ["principal_id"], unique=False)
    op.create_index(op.f("ix_audit_log_resource_grn"), "audit_log", ["resource_grn"], unique=False)
    op.create_index(
        "ix_audit_log_time_principal_decision",
        "audit_log",
        ["occurred_at", "principal_id", "decision"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_log_time_principal_decision", table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_resource_grn"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_principal_id"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_organization_id"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_occurred_at"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_event_type"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_decision"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_correlation_id"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_action"), table_name="audit_log")
    op.drop_table("audit_log")
