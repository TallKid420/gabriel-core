"""ChatRuntimeService end-to-end tests with a scriptable fake provider."""
from __future__ import annotations

import json

import pytest

from gabriel.agent.management import AgentManagementService
from gabriel.agent.repository import AgentRepository
from gabriel.conversation.message_service import MessageService
from gabriel.conversation.service import ConversationService
from gabriel.events.repository import EventRepository
from gabriel.gateway.providers.registry import ProviderRegistry
from gabriel.gateway.service import ChatRuntimeError, ChatRuntimeService
from gabriel.gateway.sessions import SessionManager
from gabriel.gateway.tools import build_default_tool_registry

from tests.gateway.conftest import FakeProvider, make_tool_call

ORG = "acme"
ALICE = "alice"


def parse_frames(frames: list[str]) -> list[tuple[str, dict]]:
    parsed = []
    for frame in frames:
        event, data = "", {}
        for line in frame.strip().splitlines():
            if line.startswith("event: "):
                event = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        parsed.append((event, data))
    return parsed


def build_runtime(session_factory, provider: FakeProvider) -> ChatRuntimeService:
    providers = ProviderRegistry(default_provider=provider.name)
    providers.register(provider)
    return ChatRuntimeService(
        session_factory=session_factory,
        providers=providers,
        tools=build_default_tool_registry(),
        sessions=SessionManager(),
    )


async def create_conversation(session_factory, agent_grn: str | None = None) -> str:
    async with session_factory() as session:
        conversation = await ConversationService(session).create_conversation(
            ORG, "Runtime test", created_by=ALICE, agent_grn=agent_grn
        )
        return str(conversation.grn)


async def create_agent(session_factory, **overrides) -> str:
    async with session_factory() as session:
        service = AgentManagementService(
            AgentRepository(session), EventRepository(session)
        )
        fields = dict(
            created_by=ALICE,
            system_prompt="You are Gabriel.",
            model_config={"provider": "fake", "model": "fake-model", "temperature": 0.2},
        )
        fields.update(overrides)
        agent = await service.create_agent(ORG, "Chat agent", **fields)
        return str(agent.grn)


@pytest.mark.asyncio
async def test_stream_turn_persists_both_messages_and_reports_usage(session_factory):
    provider = FakeProvider(script=[{"text": "Hello human"}])
    runtime = build_runtime(session_factory, provider)
    conversation_grn = await create_conversation(session_factory)

    frames = parse_frames(
        [
            f
            async for f in runtime.stream_turn(
                org_id=ORG,
                principal_id=ALICE,
                conversation_grn=conversation_grn,
                content="Hi there",
                model_override="fake-model",
            )
        ]
    )
    events = [e for e, _ in frames]
    assert events[0] == "session"
    assert "token" in events
    assert events[-1] == "done"

    done = frames[-1][1]
    assert done["usage"]["total_tokens"] == 12
    assert done["model"] == "fake-model"
    assert done["provider"] == "fake"

    tokens = "".join(d["delta"] for e, d in frames if e == "token")
    assert tokens == "Hello human"

    # Both turns persisted through the Phase-2 message service.
    async with session_factory() as session:
        items, total = await MessageService(session).list_messages(
            conversation_grn, org_id=ORG
        )
    assert total == 2
    assert [m.role.value for m in items] == ["user", "assistant"]
    assert items[0].content == "Hi there"
    assert items[1].content == "Hello human"
    assert items[1].total_tokens == 12
    assert items[1].model == "fake-model"


@pytest.mark.asyncio
async def test_stream_turn_uses_agent_configuration(session_factory):
    provider = FakeProvider(script=[{"text": "Configured reply"}])
    runtime = build_runtime(session_factory, provider)
    agent_grn = await create_agent(session_factory)
    conversation_grn = await create_conversation(session_factory, agent_grn=agent_grn)

    frames = parse_frames(
        [
            f
            async for f in runtime.stream_turn(
                org_id=ORG,
                principal_id=ALICE,
                conversation_grn=conversation_grn,
                content="Hello",
            )
        ]
    )
    session_event = dict(frames)[  # first frame
        "session"
    ]
    assert session_event["agent_grn"] == agent_grn
    assert session_event["model"] == "fake-model"

    # The provider received the agent's system prompt and temperature.
    call = provider.calls[0]
    assert call["messages"][0].role == "system"
    assert call["messages"][0].content == "You are Gabriel."
    assert call["temperature"] == 0.2


@pytest.mark.asyncio
async def test_tool_loop_executes_and_feeds_back_results(session_factory):
    provider = FakeProvider(
        script=[
            {"text": "", "tool_calls": [make_tool_call("current_datetime")]},
            {"text": "It is now."},
        ]
    )
    runtime = build_runtime(session_factory, provider)
    conversation_grn = await create_conversation(session_factory)

    frames = parse_frames(
        [
            f
            async for f in runtime.stream_turn(
                org_id=ORG,
                principal_id=ALICE,
                conversation_grn=conversation_grn,
                content="What time is it?",
                model_override="fake-model",
            )
        ]
    )
    events = [e for e, _ in frames]
    assert "tool_call" in events
    assert "tool_result" in events
    assert events[-1] == "done"

    tool_result = next(d for e, d in frames if e == "tool_result")
    assert tool_result["name"] == "current_datetime"
    assert tool_result["success"] is True
    assert "iso" in json.loads(tool_result["content"])

    # Second provider call got the tool-role message appended.
    second_call = provider.calls[1]
    tool_messages = [m for m in second_call["messages"] if m.role == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0].tool_call_id == "call-1"

    # Tool exchange is persisted for audit: user, tool, assistant.
    async with session_factory() as session:
        items, total = await MessageService(session).list_messages(
            conversation_grn, org_id=ORG
        )
    assert [m.role.value for m in items] == ["user", "tool", "assistant"]
    assert items[2].content == "It is now."


@pytest.mark.asyncio
async def test_history_is_included_in_followup_turns(session_factory):
    provider = FakeProvider(script=[{"text": "First"}, {"text": "Second"}])
    runtime = build_runtime(session_factory, provider)
    conversation_grn = await create_conversation(session_factory)

    async for _ in runtime.stream_turn(
        org_id=ORG,
        principal_id=ALICE,
        conversation_grn=conversation_grn,
        content="Turn one",
        model_override="fake-model",
    ):
        pass
    async for _ in runtime.stream_turn(
        org_id=ORG,
        principal_id=ALICE,
        conversation_grn=conversation_grn,
        content="Turn two",
        model_override="fake-model",
    ):
        pass

    second_call = provider.calls[1]
    contents = [m.content for m in second_call["messages"]]
    assert "Turn one" in contents
    assert "First" in contents
    assert contents[-1] == "Turn two"

    # One session, two turns.
    sessions = runtime.sessions.list_active(ORG)
    assert len(sessions) == 1
    assert sessions[0].turn_count == 2


@pytest.mark.asyncio
async def test_unknown_conversation_yields_error_event(session_factory):
    runtime = build_runtime(session_factory, FakeProvider())
    frames = parse_frames(
        [
            f
            async for f in runtime.stream_turn(
                org_id=ORG,
                principal_id=ALICE,
                conversation_grn="grn:acme:conversation/missing:1",
                content="Hi",
                model_override="fake-model",
            )
        ]
    )
    assert frames == [("error", {"detail": frames[0][1]["detail"]})]
    assert "not found" in frames[0][1]["detail"]


@pytest.mark.asyncio
async def test_missing_model_yields_error_event(session_factory):
    runtime = build_runtime(session_factory, FakeProvider())
    conversation_grn = await create_conversation(session_factory)
    frames = parse_frames(
        [
            f
            async for f in runtime.stream_turn(
                org_id=ORG,
                principal_id=ALICE,
                conversation_grn=conversation_grn,
                content="Hi",
            )
        ]
    )
    assert frames[0][0] == "error"
    assert "No model configured" in frames[0][1]["detail"]


@pytest.mark.asyncio
async def test_disabled_agent_is_rejected(session_factory):
    provider = FakeProvider()
    runtime = build_runtime(session_factory, provider)
    agent_grn = await create_agent(session_factory, status="inactive")
    conversation_grn = await create_conversation(session_factory, agent_grn=agent_grn)

    frames = parse_frames(
        [
            f
            async for f in runtime.stream_turn(
                org_id=ORG,
                principal_id=ALICE,
                conversation_grn=conversation_grn,
                content="Hi",
            )
        ]
    )
    assert frames[0][0] == "error"
    assert "disabled" in frames[0][1]["detail"]
    assert provider.calls == []


@pytest.mark.asyncio
async def test_complete_turn_returns_buffered_content(session_factory):
    provider = FakeProvider(script=[{"text": "Buffered answer"}])
    runtime = build_runtime(session_factory, provider)
    conversation_grn = await create_conversation(session_factory)

    result = await runtime.complete_turn(
        org_id=ORG,
        principal_id=ALICE,
        conversation_grn=conversation_grn,
        content="Hi",
        model_override="fake-model",
    )
    assert result["content"] == "Buffered answer"
    assert result["usage"]["total_tokens"] == 12
    assert result["conversation_grn"] == conversation_grn


@pytest.mark.asyncio
async def test_complete_turn_raises_on_error(session_factory):
    runtime = build_runtime(session_factory, FakeProvider())
    with pytest.raises(ChatRuntimeError, match="not found"):
        await runtime.complete_turn(
            org_id=ORG,
            principal_id=ALICE,
            conversation_grn="grn:acme:conversation/missing:1",
            content="Hi",
            model_override="fake-model",
        )
