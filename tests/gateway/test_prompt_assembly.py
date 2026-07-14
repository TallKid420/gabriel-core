"""PromptAssembler tests (Phase 3)."""
from __future__ import annotations

from datetime import datetime, timezone

from gabriel.conversation.message_models import Message, MessageRole
from gabriel.gateway.prompt import (
    ContextBlock,
    DefaultPromptStrategy,
    PromptAssembler,
    PromptRequest,
)
from gabriel.resource.grn import GRN


def _message(role: MessageRole, content: str, i: int = 0) -> Message:
    now = datetime.now(timezone.utc)
    return Message(
        grn=GRN.generate("acme", "message"),
        org_id="acme",
        created_by="alice",
        updated_by="alice",
        created_at=now,
        updated_at=now,
        conversation_grn="grn:acme:conversation/c1:1",
        role=role,
        content=content,
    )


def test_system_prompt_first_then_history_then_user():
    assembler = PromptAssembler()
    history = [
        _message(MessageRole.USER, "Hi"),
        _message(MessageRole.ASSISTANT, "Hello!"),
    ]
    messages = assembler.assemble(
        system_prompt="You are Gabriel.",
        history=history,
        user_content="What's new?",
    )
    assert [m.role for m in messages] == ["system", "user", "assistant", "user"]
    assert messages[0].content == "You are Gabriel."
    assert messages[-1].content == "What's new?"


def test_context_window_keeps_most_recent():
    history = [_message(MessageRole.USER, f"msg-{i}") for i in range(10)]
    messages = PromptAssembler().assemble(
        system_prompt="sys",
        history=history,
        user_content="now",
        context_window=3,
    )
    # system + 3 windowed history + user turn
    assert len(messages) == 5
    assert [m.content for m in messages[1:4]] == ["msg-7", "msg-8", "msg-9"]


def test_context_blocks_are_delimited_in_system_message():
    messages = PromptAssembler().assemble(
        system_prompt="You are Gabriel.",
        user_content="Hi",
        context_blocks=[
            ContextBlock(source="memory", content="User prefers metric units."),
            ContextBlock(source="tool:search", content="Result A"),
        ],
    )
    system = messages[0]
    assert system.role == "system"
    assert "[context:memory]" in system.content
    assert "User prefers metric units." in system.content
    assert "[context:tool:search]" in system.content


def test_history_system_messages_are_dropped():
    history = [
        _message(MessageRole.SYSTEM, "old system"),
        _message(MessageRole.USER, "Hi"),
        _message(MessageRole.TOOL, '{"result": 1}'),
    ]
    messages = PromptAssembler().assemble(
        system_prompt="new system", history=history, user_content="ok"
    )
    roles = [m.role for m in messages]
    assert roles == ["system", "user", "tool", "user"]
    assert messages[0].content == "new system"


def test_no_system_message_when_prompt_and_context_empty():
    messages = PromptAssembler().assemble(system_prompt="", user_content="Hi")
    assert [m.role for m in messages] == ["user"]


def test_strategy_is_swappable():
    class UppercaseStrategy:
        def build(self, request: PromptRequest):
            return DefaultPromptStrategy().build(
                PromptRequest(
                    system_prompt=request.system_prompt.upper(),
                    history=request.history,
                    user_content=request.user_content,
                    context_blocks=request.context_blocks,
                    context_window=request.context_window,
                )
            )

    assembler = PromptAssembler(strategy=UppercaseStrategy())
    messages = assembler.assemble(system_prompt="be nice", user_content="hi")
    assert messages[0].content == "BE NICE"
