"""Notification resource: a user-facing alert derived from domain events.

Notifications are Universal Resources (GRN-addressed, org-owned) addressed to
a recipient (a user GRN, falling back to a principal id for principals with no
user record). They are typically *derived* from domain events via
``NotificationService.create_from_event`` — the source event id is kept on the
notification for traceability.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from gabriel.resource.models import Resource, ResourceType


class Notification(Resource):
    """A notification addressed to a recipient within an organization."""

    resource_type: ResourceType = ResourceType.NOTIFICATION

    recipient: str
    """Recipient identifier — a user GRN (or principal id fallback)."""

    type: str
    """Notification type/category (e.g. 'resource_created', 'mention')."""

    title: str
    """Short human-readable headline."""

    body: str = ""
    """Longer human-readable body text."""

    read: bool = False
    """Whether the recipient has read the notification."""

    read_at: datetime | None = None
    """When the notification was marked read."""

    source_event_id: str | None = None
    """Id of the domain event this notification was derived from."""

    def public_view(self) -> dict[str, Any]:
        """Serializable representation safe to return from the API."""
        return {
            "grn": str(self.grn),
            "org_id": self.org_id,
            "recipient": self.recipient,
            "type": self.type,
            "title": self.title,
            "body": self.body,
            "read": self.read,
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "source_event_id": self.source_event_id,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }
