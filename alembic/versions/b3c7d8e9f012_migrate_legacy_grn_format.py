"""migrate_legacy_grn_format

Revision ID: b3c7d8e9f012
Revises: ae642da113fe
Create Date: 2026-06-29 00:00:00.000000

"""
from __future__ import annotations

import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b3c7d8e9f012"
down_revision: Union[str, Sequence[str], None] = "ae642da113fe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_LEGACY_RE = re.compile(r"^grn://([^/]+)/([^/]+)/(.+)@(\d+)$")
_CANONICAL_RE = re.compile(r"^grn:([^:]+):([^/]+)/(.+):(\d+)$")


def _legacy_to_canonical(value: str) -> str:
    match = _LEGACY_RE.match(value)
    if not match:
        return value
    org_id, resource_type, resource_id, version = match.groups()
    return f"grn:{org_id}:{resource_type}/{resource_id}:{version}"


def _canonical_to_legacy(value: str) -> str:
    match = _CANONICAL_RE.match(value)
    if not match:
        return value
    org_id, resource_type, resource_id, version = match.groups()
    return f"grn://{org_id}/{resource_type}/{resource_id}@{version}"


def _rewrite_organizations_grn(converter) -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT grn FROM organizations")).fetchall()

    for (old_grn,) in rows:
        new_grn = converter(old_grn)
        if new_grn != old_grn:
            bind.execute(
                sa.text("UPDATE organizations SET grn = :new_grn WHERE grn = :old_grn"),
                {"new_grn": new_grn, "old_grn": old_grn},
            )


def upgrade() -> None:
    """Rewrite persisted GRNs from legacy URI format to canonical colon format.

    This migration currently updates the organizations table, which is the only
    persisted resource table in this repository at this point.
    """
    _rewrite_organizations_grn(_legacy_to_canonical)


def downgrade() -> None:
    """Rewrite persisted GRNs from canonical colon format back to legacy URI format."""
    _rewrite_organizations_grn(_canonical_to_legacy)
