"""Human-in-the-loop tool approval bridge tests (Fix 2).

Covers the ``REQUIRES_CONFIRMATION`` flow end-to-end:
* the stream emits ``tool_approval_required`` and pauses;
* accept → the tool executes and the result flows back to the LLM;
* deny → the tool is skipped and an informative message is injected.
"""
from __future__ import annotations

import json

import pytest

from gabriel.agent.grn_bindings import tool_grn
from gabriel.gateway.service import ChatRuntimeService
from gabriel.tool.discovery import tool_indexer
from gabriel.tool.models import SafetyLevel, ToolCategory
from gabriel.tool.repository import ToolRepository
from gabriel.tool.service import ToolService

from tests.gateway.conftest import FakeProvider, make_tool_call
from tests.gateway.test_chat_runtime import (
    ALICE,
    ORG,
    build_runtime,
    create_agent,
    create_conversation,
    parse_frames,
)


async def enable_confirm_tool(session_factory, name: str) -> None:
    """Create an *enabled* REQUIRES_CONFIRMATION Tool row for ``name``."""
    catalog = {t.name: t for t in tool_indexer.discover()}
    discovered = catalog[name]
    async with session_factory() as session:
        service = ToolService(ToolRepository(session))
        await service.create_tool(
            org_id=ORG,
            created_by=ALICE,
            name=name,
            description=discovered.description,
            category=ToolCategory.UTILITY,
            parameters=discovered.parameters,
            safety_level=SafetyLevel.REQUIRES_CONFIRMATION,
            runtime_binding=discovered.runtime_binding,
            enabled=True,
            tool_grn=tool_grn(name, ORG, version=1),
        )


async def _collect_with_decision(
    runtime: ChatRuntimeService,
    *,
    conversation_grn: str,
    approved: bool,
    deny_reason: str | None = None,
) -> list[tuple[str, dict]]:
    """Drive the stream, answering the first approval prompt with a decision."""
    frames: list[str] = []
    gen = runtime.stream_turn(
        org_id=ORG,
        principal_id=ALICE,
        conversation_grn=conversation_grn,
        content="Please run the tool",
        model_override="fake-model",
    )
    async for frame in gen:
        frames.append(frame)
        event, data = parse_frames([frame])[0]
        if event == "tool_approval_required":
            # The generator is suspended right after emitting this event and
            # will await the decision on the next iteration — resolve it now.
            runtime.submit_approval(
                session_id=data["session_id"],
                tool_name=data["tool_name"],
                approved=approved,
                deny_reason=deny_reason,
            )
    return parse_frames(frames)


@pytest.mark.asyncio
async def test_confirmation_tool_accept_executes(session_factory):
    provider = FakeProvider(
        script=[
            {"text": "", "tool_calls": [make_tool_call("calculate", expression="2 + 2")]},
            {"text": "The answer is 4."},
        ]
    )
    runtime = build_runtime(session_factory, provider)
    await enable_confirm_tool(session_factory, "calculate")
    agent_grn = await create_agent(session_factory, allowed_tools=["calculate"])
    conversation_grn = await create_conversation(session_factory, agent_grn=agent_grn)

    frames = await _collect_with_decision(
        runtime, conversation_grn=conversation_grn, approved=True
    )
    events = [e for e, _ in frames]

    assert "tool_approval_required" in events
    assert "tool_result" in events
    result = next(d for e, d in frames if e == "tool_result")
    assert result["success"] is True
    assert result["denied"] is False
    assert json.loads(result["content"])["result"] == 4


@pytest.mark.asyncio
async def test_confirmation_tool_deny_skips_execution(session_factory):
    provider = FakeProvider(
        script=[
            {"text": "", "tool_calls": [make_tool_call("calculate", expression="2 + 2")]},
            {"text": "Understood, I will not run it."},
        ]
    )
    runtime = build_runtime(session_factory, provider)
    await enable_confirm_tool(session_factory, "calculate")
    agent_grn = await create_agent(session_factory, allowed_tools=["calculate"])
    conversation_grn = await create_conversation(session_factory, agent_grn=agent_grn)

    frames = await _collect_with_decision(
        runtime,
        conversation_grn=conversation_grn,
        approved=False,
        deny_reason="Not now",
    )
    events = [e for e, _ in frames]

    assert "tool_approval_required" in events
    result = next(d for e, d in frames if e == "tool_result")
    assert result["denied"] is True
    assert result["success"] is False
    payload = json.loads(result["content"])
    assert payload["denied"] is True
    assert "denied execution of tool 'calculate'" in payload["message"]
    assert "Not now" in payload["message"]

    # The denial was fed back to the LLM as a tool-role message.
    second_call = provider.calls[1]
    tool_messages = [m for m in second_call["messages"] if m.role == "tool"]
    assert tool_messages and "denied execution" in tool_messages[0].content
