"""Notification service.

Creates notifications (directly or derived from domain events), lists them per
recipient, and manages read state. Notification writes emit their own
``notification_*`` events in the same transaction (ADR-017), keeping the audit
trail complete without recursive notification fan-out (notification events are
never themselves turned into notifications).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from gabriel.events.event import Event
from gabriel.events.repository import EventRepository
from gabriel.notification.mappers import domain_to_orm, orm_to_domain
from gabriel.notification.models import Notification
from gabriel.notification.repository import NotificationRepository
from gabriel.resource.bootstrap import register_core_resource_types
from gabriel.resource.factory import ResourceFactory
from gabriel.resource.grn import GRN
from gabriel.resource.models import ResourceState
from gabriel.resource.registry import registry


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Default headline templates for well-known domain event types. Anything not
# listed falls back to a generic title derived from the event type.
_EVENT_TITLES: dict[str, str] = {
    "resource_created": "A new {resource_type} was created",
    "resource_updated": "A {resource_type} was updated",
    "resource_deleted": "A {resource_type} was deleted",
    "message_created": "New message in a conversation",
    "user_password_changed": "Your password was changed",
    "member_added": "A new member joined your organization",
    "member_removed": "A member left your organization",
    "member_role_changed": "A member's role changed",
}


def _title_for_event(event: Event) -> str:
    template = _EVENT_TITLES.get(event.type)
    resource_type = str(event.payload.get("resource_type", "resource"))
    if template:
        return template.format(resource_type=resource_type)
    return event.type.replace("_", " ").capitalize()


class NotificationService:
    """Business logic for notifications (org- and recipient-scoped)."""

    def __init__(self, session: AsyncSession, event_repo: EventRepository | None = None):
        register_core_resource_types()
        self.session = session
        self.repo = NotificationRepository(session)
        self.event_repo = event_repo or EventRepository(session)
        self.factory = ResourceFactory(registry)

    # ── Creation ─────────────────────────────────────────────────────────────

    async def create_notification(
        self,
        org_id: str,
        recipient: str,
        *,
        type: str,
        title: str,
        body: str = "",
        created_by: str = "system",
        source_event_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        commit: bool = True,
    ) -> Notification:
        """Create a notification and its audit event atomically."""
        grn = GRN.generate(org_id=org_id, resource_type="notification")
        notification: Notification = self.factory.create(
            "notification",
            grn=grn,
            org_id=org_id,
            state=ResourceState.ACTIVE,
            created_by=created_by,
            updated_by=created_by,
            recipient=recipient,
            type=type,
            title=title,
            body=body,
            source_event_id=source_event_id,
            metadata=metadata or {},
        )
        orm = await self.repo.create(domain_to_orm(notification))
        await self.event_repo.append(
            Event(
                type="notification_created",
                principal_id=created_by,
                organization_id=org_id,
                resource_grn=str(grn),
                correlation_id=correlation_id,
                causation_id=source_event_id,
                payload={
                    "resource_type": "notification",
                    "grn": str(grn),
                    "recipient": recipient,
                    "notification_type": type,
                    "source_event_id": source_event_id,
                },
                metadata={"service": "NotificationService", "operation": "create_notification"},
            )
        )
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
        return orm_to_domain(orm)

    async def create_from_event(
        self,
        event: Event,
        recipient: str,
        *,
        title: str | None = None,
        body: str | None = None,
        metadata: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> Notification:
        """Derive a notification from a domain event (the primary write path).

        The notification's type mirrors the event type, its ``causation_id``
        chain points at the source event, and the payload carries a compact
        summary so the UI does not need to re-fetch the event.
        """
        return await self.create_notification(
            event.organization_id,
            recipient,
            type=event.type,
            title=title or _title_for_event(event),
            body=body
            or str(event.payload.get("summary", ""))
            or f"Event {event.type} on {event.resource_grn or 'organization'}",
            created_by=event.principal_id,
            source_event_id=event.id,
            metadata={
                "resource_grn": event.resource_grn,
                **(metadata or {}),
            },
            correlation_id=event.correlation_id,
            commit=commit,
        )

    # ── Read state ───────────────────────────────────────────────────────────

    async def mark_read(
        self,
        grn_str: str,
        *,
        org_id: str,
        recipient: str,
        read_by: str,
        correlation_id: str | None = None,
    ) -> Notification:
        """Mark a single notification read (idempotent)."""
        orm = await self.repo.get_by_grn(grn_str, org_id=org_id, recipient=recipient)
        if not orm.read:
            orm.read = True
            orm.read_at = utcnow()
            orm.version += 1
            orm.updated_by = read_by
            await self.event_repo.append(
                Event(
                    type="notification_read",
                    principal_id=read_by,
                    organization_id=org_id,
                    resource_grn=grn_str,
                    correlation_id=correlation_id,
                    payload={"grn": grn_str},
                    metadata={"service": "NotificationService", "operation": "mark_read"},
                )
            )
        await self.session.commit()
        return orm_to_domain(orm)

    async def mark_all_read(
        self,
        org_id: str,
        recipient: str,
        *,
        read_by: str,
        correlation_id: str | None = None,
    ) -> int:
        """Mark all of a recipient's unread notifications as read."""
        count = await self.repo.mark_all_read(org_id, recipient)
        if count:
            await self.event_repo.append(
                Event(
                    type="notifications_all_read",
                    principal_id=read_by,
                    organization_id=org_id,
                    correlation_id=correlation_id,
                    payload={"recipient": recipient, "count": count},
                    metadata={"service": "NotificationService", "operation": "mark_all_read"},
                )
            )
        await self.session.commit()
        return count

    # ── Queries ──────────────────────────────────────────────────────────────

    async def get_notification(
        self, grn_str: str, *, org_id: str, recipient: str | None = None
    ) -> Notification:
        return orm_to_domain(
            await self.repo.get_by_grn(grn_str, org_id=org_id, recipient=recipient)
        )

    async def list_notifications(
        self,
        org_id: str,
        recipient: str,
        *,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Notification], int]:
        """Paginated recipient-scoped listing; returns (items, total)."""
        orms, total = await self.repo.list_for_recipient(
            org_id, recipient, unread_only=unread_only, limit=limit, offset=offset
        )
        return [orm_to_domain(orm) for orm in orms], total

    async def unread_count(self, org_id: str, recipient: str) -> int:
        return await self.repo.unread_count(org_id, recipient)
