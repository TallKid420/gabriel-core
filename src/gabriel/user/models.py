"""User resource: a human account within an organization.

A User is a Universal Resource (GRN-addressed, versioned, org-owned) that is
mirrored by a Principal (the identity primitive used for authentication and
PEEL evaluation). The split follows ADR-001 (principal/resource mirroring):

* ``User`` (resource)  — profile, credentials, lifecycle; managed via CRUD.
* ``Principal`` (identity) — what authenticates and acts; carries capabilities.

The password hash is stored on the user record but must never be serialized
out through the API — use :meth:`User.public_view`.
"""
from __future__ import annotations

from typing import Any

from pydantic import Field

from gabriel.resource.models import Resource, ResourceType


class User(Resource):
    """A human user account, scoped to an organization."""

    resource_type: ResourceType = ResourceType.USER

    email: str
    """Login email. Unique within the owning organization."""

    display_name: str
    """Human-readable name."""

    principal_id: str
    """Mirrored Principal identifier (principal://org/user/<identifier>)."""

    password_hash: str | None = Field(default=None, repr=False, exclude=True)
    """Encoded password hash (see identity.passwords). Excluded from dumps."""

    def public_view(self) -> dict[str, Any]:
        """Serializable representation safe to return from the API."""
        return {
            "grn": str(self.grn),
            "org_id": self.org_id,
            "email": self.email,
            "display_name": self.display_name,
            "principal_id": self.principal_id,
            "state": self.state.value,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
            "labels": self.labels,
        }
