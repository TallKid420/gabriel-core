from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gabriel.identity.principal import Principal
from gabriel.api.schema import Notification

# grn:organization:notification/source:int
MOCK_NOTIFICATIONS = [
    {
    'grn': 'grn:organization:notification/chat:1',
    'level': 'info',
    'title': 'Claim assigned to you',
    'body': 'Water damage claim — 428 Elm St was routed to M. Reyes.',
    'created_at': '2026-06-30T02:11:00Z',
    'read': False,
    },
    {
    'grn': 'grn:organization:notification/chat:2',
    'level': 'warning',
    'title': 'Underwriting review needed',
    'body': '90 Harbor Blvd flagged 3 risk factors.',
    'created_at': '2026-06-29T16:46:00Z',
    'read': False,
    },
    {
    'grn': 'grn:organization:notification/documents:1',
    'level': 'success',
    'title': 'Document ready',
    'body': 'HO-3 Master Form finished processing.',
    'created_at': '2026-06-30T00:11:00Z',
    'read': True,
    },
]

class NotificationRepository:
    """Repository over the gateway's in-memory resource projection."""

    def __init__(self, resource_projection) -> None:
        self._resource_projection = resource_projection

    def get_notifications(self, organization_id: str) -> list[Notification]:
        # Placeholder implementation for fetching notifications
        return [Notification(**notification) for notification in MOCK_NOTIFICATIONS]

        # Placeholder implmentation.
        resources = self._resource_projection.list_resources(
            organization_id=organization_id,
            resource_type="notification",
        )
        return [Notification(**resource) for resource in resources]
    
    def mark_all_read(self, organization_id: str) -> None:
        # Placeholder implementation for marking all notifications as read
        pass

    def change_read_status(self, organization_id: str, notification_grn: str) -> None:
        # Placeholder implementation for changing the read status of a notification
        pass

class NotificationService:
    """Application service for notification listing and future policy-backed access checks."""

    def __init__(self, repository: NotificationRepository) -> None:
        self._repository = repository

    def get_notifications(self, principal: Principal) -> list[Notification]:
        resources = self._repository.get_notifications(principal.organization_id)
        return resources
    
    def mark_all_read(self, principal: Principal) -> None:
        self._repository.mark_all_read(principal.organization_id)

    def change_read_status(self, principal: Principal, notification_grn: str) -> None:
        self._repository.change_read_status(principal.organization_id, notification_grn)