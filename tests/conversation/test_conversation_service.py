"""Tests for ConversationService (Phase 2 — Core Business Logic)."""
import pytest
from sqlalchemy import select

from gabriel.conversation.models import ConversationStatus
from gabriel.conversation.service import ConversationService
from gabriel.events.orm import EventORM
from gabriel.resource.exceptions import ResourceNotFoundError

pytestmark = pytest.mark.asyncio

ORG = "acme"
ACTOR = "principal-1"


async def _create(service: ConversationService, title: str = "Support thread", **kw):
    return await service.create_conversation(ORG, title, created_by=ACTOR, **kw)


async def test_create_conversation_mints_grn_and_defaults(db_session):
    service = ConversationService(db_session)
    conversation = await _create(service, agent_grn="grn:acme:agent/a1:1")

    assert str(conversation.grn).startswith("grn:acme:conversation/")
    assert conversation.title == "Support thread"
    assert conversation.status == ConversationStatus.ACTIVE
    assert conversation.participants == [ACTOR]
    assert conversation.agent_grn == "grn:acme:agent/a1:1"
    assert conversation.org_id == ORG


async def test_create_appends_resource_created_event(db_session):
    service = ConversationService(db_session)
    conversation = await _create(service)

    result = await db_session.execute(
        select(EventORM).filter_by(resource_grn=str(conversation.grn))
    )
    events = list(result.scalars())
    assert len(events) == 1
    assert events[0].type == "resource_created"
    assert events[0].payload["resource_type"] == "conversation"


async def test_get_conversation_org_scoped(db_session):
    service = ConversationService(db_session)
    conversation = await _create(service)

    fetched = await service.get_conversation(str(conversation.grn), org_id=ORG)
    assert fetched.grn == conversation.grn

    with pytest.raises(ResourceNotFoundError):
        await service.get_conversation(str(conversation.grn), org_id="other-org")


async def test_list_conversations_paginated(db_session):
    service = ConversationService(db_session)
    for i in range(5):
        await _create(service, title=f"Thread {i}")

    page, total = await service.list_conversations(ORG, limit=2, offset=0)
    assert total == 5
    assert len(page) == 2

    rest, total = await service.list_conversations(ORG, limit=10, offset=4)
    assert total == 5
    assert len(rest) == 1


async def test_list_filters_by_status(db_session):
    service = ConversationService(db_session)
    keep = await _create(service, title="keep")
    to_archive = await _create(service, title="archive me")
    await service.archive_conversation(str(to_archive.grn), archived_by=ACTOR, org_id=ORG)

    active, total_active = await service.list_conversations(
        ORG, status=ConversationStatus.ACTIVE
    )
    archived, total_archived = await service.list_conversations(ORG, status="archived")

    assert total_active == 1 and active[0].grn == keep.grn
    assert total_archived == 1 and archived[0].grn == to_archive.grn


async def test_update_conversation_bumps_version(db_session):
    service = ConversationService(db_session)
    conversation = await _create(service)

    updated = await service.update_conversation(
        str(conversation.grn),
        updated_by=ACTOR,
        org_id=ORG,
        title="Renamed",
        participants=[ACTOR, "user-2"],
    )
    assert updated.title == "Renamed"
    assert updated.participants == [ACTOR, "user-2"]
    assert updated.version == conversation.version + 1


async def test_delete_is_soft_and_hides_from_reads(db_session):
    service = ConversationService(db_session)
    conversation = await _create(service)

    await service.delete_conversation(str(conversation.grn), deleted_by=ACTOR, org_id=ORG)

    with pytest.raises(ResourceNotFoundError):
        await service.get_conversation(str(conversation.grn), org_id=ORG)

    _, total = await service.list_conversations(ORG)
    assert total == 0
