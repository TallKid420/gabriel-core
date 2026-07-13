"""Tests for MessageService (Phase 2 — Core Business Logic)."""
import pytest
from sqlalchemy import select

from gabriel.conversation.message_models import MessageRole
from gabriel.conversation.message_service import ConversationClosedError, MessageService
from gabriel.conversation.service import ConversationService
from gabriel.events.orm import EventORM
from gabriel.resource.exceptions import ResourceNotFoundError

pytestmark = pytest.mark.asyncio

ORG = "acme"
ACTOR = "principal-1"


async def _conversation(db_session):
    return await ConversationService(db_session).create_conversation(
        ORG, "Thread", created_by=ACTOR
    )


async def test_create_message_defaults_total_tokens(db_session):
    conversation = await _conversation(db_session)
    service = MessageService(db_session)

    message = await service.create_message(
        str(conversation.grn),
        org_id=ORG,
        created_by=ACTOR,
        role="assistant",
        content="Hello!",
        prompt_tokens=10,
        completion_tokens=5,
        model="gpt-test",
    )

    assert str(message.grn).startswith("grn:acme:message/")
    assert message.role == MessageRole.ASSISTANT
    assert message.total_tokens == 15
    assert message.model == "gpt-test"
    assert message.conversation_grn == str(conversation.grn)


async def test_create_message_emits_event(db_session):
    conversation = await _conversation(db_session)
    message = await MessageService(db_session).create_message(
        str(conversation.grn), org_id=ORG, created_by=ACTOR, role="user", content="Hi"
    )

    result = await db_session.execute(
        select(EventORM).filter_by(resource_grn=str(message.grn))
    )
    events = list(result.scalars())
    assert len(events) == 1
    assert events[0].type == "message_created"
    assert events[0].payload["conversation_grn"] == str(conversation.grn)


async def test_create_message_unknown_conversation(db_session):
    service = MessageService(db_session)
    with pytest.raises(ResourceNotFoundError):
        await service.create_message(
            "grn:acme:conversation/does-not-exist:1",
            org_id=ORG,
            created_by=ACTOR,
            role="user",
            content="Hi",
        )


async def test_create_message_rejected_for_archived_conversation(db_session):
    conversation = await _conversation(db_session)
    await ConversationService(db_session).archive_conversation(
        str(conversation.grn), archived_by=ACTOR, org_id=ORG
    )

    with pytest.raises(ConversationClosedError):
        await MessageService(db_session).create_message(
            str(conversation.grn), org_id=ORG, created_by=ACTOR, role="user", content="Hi"
        )


async def test_list_messages_paginated_chronological(db_session):
    conversation = await _conversation(db_session)
    service = MessageService(db_session)
    for i in range(5):
        await service.create_message(
            str(conversation.grn),
            org_id=ORG,
            created_by=ACTOR,
            role="user",
            content=f"msg {i}",
        )

    page, total = await service.list_messages(
        str(conversation.grn), org_id=ORG, limit=3, offset=0
    )
    assert total == 5
    assert [m.content for m in page] == ["msg 0", "msg 1", "msg 2"]

    rest, _ = await service.list_messages(
        str(conversation.grn), org_id=ORG, limit=3, offset=3
    )
    assert [m.content for m in rest] == ["msg 3", "msg 4"]
