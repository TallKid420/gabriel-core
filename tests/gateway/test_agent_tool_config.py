"""Agent-configuration-driven tool & grounding resolution (V1).

Covers the deny-wins tool allow-list (agent ``disabled_tools`` and
org-disabled Tool resources) and document-collection grounding in
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
            input_schema={},
            output_schema={},
            safety_level=0,
            required_capabilities=[],
            enabled=enabled,
        )


@pytest.mark.asyncio
async def test_disabled_tools_are_subtracted_from_declared_tools(session_factory):
    runtime = build_runtime(session_factory, FakeProvider(script=[{"text": "hi"}]))
    agent_grn = await create_agent(
        session_factory,
        allowed_tools=["current_datetime", "web_search"],
        disabled_tools=["web_search"],
    )
    conversation = await _get_conversation(session_factory, agent_grn)

    config = await _resolve(session_factory, runtime, conversation)

    assert config.allowed_tools == ["current_datetime"]


@pytest.mark.asyncio
async def test_org_disabled_tool_resource_wins_over_agent_declaration(
    session_factory,
):
    runtime = build_runtime(session_factory, FakeProvider(script=[{"text": "hi"}]))
    await _register_tool(session_factory, "current_datetime", enabled=False)
    agent_grn = await create_agent(
        session_factory, allowed_tools=["current_datetime", "echo"]
    )
    conversation = await _get_conversation(session_factory, agent_grn)

    config = await _resolve(session_factory, runtime, conversation)

    assert config.allowed_tools == ["echo"]


@pytest.mark.asyncio
async def test_agent_without_declared_or_disabled_tools_is_unrestricted(
    session_factory,
):
    runtime = build_runtime(session_factory, FakeProvider(script=[{"text": "hi"}]))
    await _register_tool(session_factory, "some_enabled_tool", enabled=True)
    agent_grn = await create_agent(session_factory)
    conversation = await _get_conversation(session_factory, agent_grn)

    config = await _resolve(session_factory, runtime, conversation)

    assert config.allowed_tools is None  # preserved prior semantics


@pytest.mark.asyncio
async def test_org_disabled_tool_restricts_undeclared_agent(session_factory):
    """No declared tools + an org-disabled tool = registry minus disabled."""
    runtime = build_runtime(session_factory, FakeProvider(script=[{"text": "hi"}]))
    await _register_tool(session_factory, "current_datetime", enabled=False)
    agent_grn = await create_agent(session_factory)
    conversation = await _get_conversation(session_factory, agent_grn)

    config = await _resolve(session_factory, runtime, conversation)

    # Default runtime registry contains only current_datetime.
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
