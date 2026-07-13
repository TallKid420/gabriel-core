"""Tests for NotificationService (Phase 2 — Core Business Logic)."""
import pytest
from sqlalchemy import select

from gabriel.events.event import Event
from gabriel.events.orm import EventORM
from gabriel.notification.service import NotificationService
from gabriel.resource.exceptions import ResourceNotFoundError

pytestmark = pytest.mark.asyncio

ORG = "acme"
RECIPIENT = "grn:acme:user/u1:1"
OTHER = "grn:acme:user/u2:1"


async def _notify(service: NotificationService, recipient: str = RECIPIENT, **kw):
    defaults = dict(type="resource_created", title="Something happened", body="details")
    defaults.update(kw)
    return await service.create_notification(ORG, recipient, **defaults)


async def test_create_notification(db_session):
    service = NotificationService(db_session)
    notification = await _notify(service)

    assert str(notification.grn).startswith("grn:acme:notification/")
    assert notification.recipient == RECIPIENT
    assert notification.read is False
    assert notification.read_at is None


async def test_create_from_event_derives_fields(db_session):
    service = NotificationService(db_session)
    event = Event(
        type="resource_created",
        principal_id="principal-9",
        organization_id=ORG,
        resource_grn="grn:acme:agent/a1:1",
        payload={"resource_type": "agent"},
    )

    notification = await service.create_from_event(event, RECIPIENT)

    assert notification.type == "resource_created"
    assert notification.title == "A new agent was created"
    assert notification.source_event_id == event.id
    assert notification.recipient == RECIPIENT
    assert notification.metadata["resource_grn"] == "grn:acme:agent/a1:1"


async def test_mark_read_is_idempotent_and_audited(db_session):
    service = NotificationService(db_session)
    notification = await _notify(service)

    first = await service.mark_read(
        str(notification.grn), org_id=ORG, recipient=RECIPIENT, read_by="principal-1"
    )
    assert first.read is True
    assert first.read_at is not None

    again = await service.mark_read(
        str(notification.grn), org_id=ORG, recipient=RECIPIENT, read_by="principal-1"
    )
    assert again.read is True
    assert again.version == first.version  # no double bump

    result = await db_session.execute(select(EventORM).filter_by(type="notification_read"))
    assert len(list(result.scalars())) == 1


async def test_mark_read_scoped_to_recipient(db_session):
    service = NotificationService(db_session)
    notification = await _notify(service)

    with pytest.raises(ResourceNotFoundError):
        await service.mark_read(
            str(notification.grn), org_id=ORG, recipient=OTHER, read_by="principal-2"
        )


async def test_mark_all_read_and_unread_count(db_session):
    service = NotificationService(db_session)
    for _ in range(3):
        await _notify(service)
    await _notify(service, recipient=OTHER)

    assert await service.unread_count(ORG, RECIPIENT) == 3

    count = await service.mark_all_read(ORG, RECIPIENT, read_by="principal-1")
    assert count == 3
    assert await service.unread_count(ORG, RECIPIENT) == 0
    # Other recipients untouched.
    assert await service.unread_count(ORG, OTHER) == 1


async def test_list_notifications_unread_filter(db_session):
    service = NotificationService(db_session)
    a = await _notify(service, title="first")
    await _notify(service, title="second")
    await service.mark_read(str(a.grn), org_id=ORG, recipient=RECIPIENT, read_by="p")

    unread, total_unread = await service.list_notifications(
        ORG, RECIPIENT, unread_only=True
    )
    everything, total = await service.list_notifications(ORG, RECIPIENT)

    assert total_unread == 1 and unread[0].title == "second"
    assert total == 2
