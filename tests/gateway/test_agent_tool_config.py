"""Agent-configuration-driven tool & grounding resolution (V1).

Covers the opt-in tool allow-list — a tool is only exposed when it is
simultaneously present in the discovery catalog, backed by an *enabled*
``Tool`` resource for the org, and allowed by the agent's declared/disabled
tools (deny-wins) — plus document-collection grounding in
``ChatRuntimeService.resolve_config``.
"""
from __future__ import annotations

import pytest

from gabriel.conversation.service import ConversationService
from gabriel.events.repository import EventRepository
from gabriel.tool.repository import ToolRepository
from gabriel.tool.service import ToolService

from tests.gateway.conftest import FakeProvider
from tests.gateway.test_chat_runtime import (
    ALICE,
    ORG,
    build_runtime,
    create_agent,
)


async def _get_conversation(session_factory, agent_grn: str):
    async with session_factory() as session:
        service = ConversationService(session)
        conversation = await service.create_conversation(
            ORG, "Config test", created_by=ALICE, agent_grn=agent_grn
        )
        return conversation


async def _resolve(session_factory, runtime, conversation):
    async with session_factory() as session:
        return await runtime.resolve_config(
            session, conversation=conversation, org_id=ORG
        )


async def _register_tool(session_factory, name: str, *, enabled: bool) -> None:
    async with session_factory() as session:
        service = ToolService(ToolRepository(session), EventRepository(session))
        await service.create_tool(
            ORG,
            ALICE,
            name=name,
            description=f"{name} tool",
            category="utility",
            parameters={},
            safety_level=0,
            enabled=enabled,
        )


@pytest.mark.asyncio
async def test_disabled_tools_are_subtracted_from_declared_tools(session_factory):
    runtime = build_runtime(session_factory, FakeProvider(script=[{"text": "hi"}]))
    await _register_tool(session_factory, "get_time", enabled=True)
    await _register_tool(session_factory, "calculate", enabled=True)
    agent_grn = await create_agent(
        session_factory,
        allowed_tools=["get_time", "calculate"],
        disabled_tools=["calculate"],
    )
    conversation = await _get_conversation(session_factory, agent_grn)

    config = await _resolve(session_factory, runtime, conversation)

    assert config.allowed_tools == ["get_time"]


@pytest.mark.asyncio
async def test_org_disabled_tool_resource_wins_over_agent_declaration(
    session_factory,
):
    runtime = build_runtime(session_factory, FakeProvider(script=[{"text": "hi"}]))
    await _register_tool(session_factory, "get_time", enabled=False)
    await _register_tool(session_factory, "calculate", enabled=True)
    agent_grn = await create_agent(
        session_factory, allowed_tools=["get_time", "calculate"]
    )
    conversation = await _get_conversation(session_factory, agent_grn)

    config = await _resolve(session_factory, runtime, conversation)

    assert config.allowed_tools == ["calculate"]


@pytest.mark.asyncio
async def test_agent_without_declared_tools_gets_all_org_enabled_tools(
    session_factory,
):
    runtime = build_runtime(session_factory, FakeProvider(script=[{"text": "hi"}]))
    await _register_tool(session_factory, "get_time", enabled=True)
    agent_grn = await create_agent(session_factory)
    conversation = await _get_conversation(session_factory, agent_grn)

    config = await _resolve(session_factory, runtime, conversation)

    # No declared tools: base is every catalog tool backed by an enabled
    # Tool resource for the org.
    assert config.allowed_tools == ["get_time"]


@pytest.mark.asyncio
async def test_org_disabled_tool_restricts_undeclared_agent(session_factory):
    """No declared tools + no enabled Tool resources = no tools exposed."""
    runtime = build_runtime(session_factory, FakeProvider(script=[{"text": "hi"}]))
    await _register_tool(session_factory, "get_time", enabled=False)
    agent_grn = await create_agent(session_factory)
    conversation = await _get_conversation(session_factory, agent_grn)

    config = await _resolve(session_factory, runtime, conversation)

    assert config.allowed_tools == []


@pytest.mark.asyncio
async def test_document_collections_feed_grounding_sources(session_factory):
    runtime = build_runtime(session_factory, FakeProvider(script=[{"text": "hi"}]))
    ks = f"grn:{ORG}:knowledge_source/aaaa:1"
    dc = f"grn:{ORG}:knowledge_source/bbbb:1"
    agent_grn = await create_agent(
        session_factory,
        knowledge_sources=[ks],
        document_collections=[dc, ks],  # duplicate on purpose
    )
    conversation = await _get_conversation(session_factory, agent_grn)

    config = await _resolve(session_factory, runtime, conversation)

    assert config.knowledge_sources == (ks,)
    assert config.document_collections == (dc, ks)
    # grounding_sources deduplicates while preserving order.
    assert config.grounding_sources() == [ks, dc]
