"""add users, org_memberships, refresh_tokens tables (+ merge heads)

Revision ID: i9c3d5e7f1a2
Revises: a1c9e4d7f2b3, b3c7d8e9f012, h2b4c6d8e0f1
Create Date: 2026-07-12 00:00:00.000000

Implements: Phase 1 — Core Backend Foundations
            (password authentication, user management, org membership)

Changes
-------
1. Merge the three outstanding migration heads into a single lineage.
2. Create ``users`` — User resources (GRN-addressed, org-scoped accounts with
   password hashes; email unique per organization).
3. Create ``org_memberships`` — principal seats within an organization,
   carrying the org role (owner/admin/member/viewer).
4. Create ``refresh_tokens`` — hashed, single-use, rotating refresh tokens.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "i9c3d5e7f1a2"
down_revision: Union[str, Sequence[str], None] = (
    "a1c9e4d7f2b3",
    "b3c7d8e9f012",
    "h2b4c6d8e0f1",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users — the User resource (mirrors GabrielResourceMixin columns)
    op.create_table(
        "users",
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
        sa.Column("email", sa.String(320), nullable=False, index=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("principal_id", sa.String(225), nullable=False, unique=True, index=True),
        sa.Column("password_hash", sa.String(512), nullable=True),
        sa.UniqueConstraint("org_id", "email", name="uq_users_org_email"),
    )

    # 2. org_memberships — principal seats within an organization
    op.create_table(
        "org_memberships",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("org_id", sa.String(128), nullable=False, index=True),
        sa.Column("principal_id", sa.String(225), nullable=False, index=True),
        sa.Column("user_grn", sa.String(255), nullable=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "org_id", "principal_id", name="uq_membership_org_principal"
        ),
    )

    # 3. refresh_tokens — hashed, single-use, rotating session renewal
    op.create_table(
        "refresh_tokens",
        sa.Column("token_hash", sa.String(64), primary_key=True, nullable=False),
        sa.Column("principal_id", sa.String(225), nullable=False, index=True),
        sa.Column("org_id", sa.String(128), nullable=False, index=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_hash", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("refresh_tokens")
    op.drop_table("org_memberships")
    op.drop_table("users")
