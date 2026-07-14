"""Prompt assembly (Phase 3 — Gateway AI Runtime).

Builds the neutral prompt payload sent to an LLM provider from three inputs:

1. the agent's ``system_prompt``;
2. the conversation history (trimmed to a configurable context window);
3. injected context blocks (memory recall, tool results, RAG chunks …).

The assembly algorithm is a pluggable *strategy* so alternative prompting
schemes (e.g. summarising long histories instead of truncating) can be
swapped in without touching the runtime.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from gabriel.conversation.message_models import Message, MessageRole
from gabriel.gateway.providers.base import ChatMessage

DEFAULT_CONTEXT_WINDOW = 20


@dataclass(frozen=True)
class ContextBlock:
    """A named block of injected context (memory, tool output, documents)."""

    source: str
    """Where the context came from, e.g. ``"memory"`` or ``"tool:search"``."""

    content: str
    """The context text itself."""


@dataclass(frozen=True)
class PromptRequest:
    """Everything a strategy needs to build a provider payload."""

    system_prompt: str
    history: list[Message] = field(default_factory=list)
    user_content: str = ""
    context_blocks: list[ContextBlock] = field(default_factory=list)
    context_window: int = DEFAULT_CONTEXT_WINDOW
    """Maximum number of history messages included (most recent kept)."""


@runtime_checkable
class PromptStrategy(Protocol):
    """Turns a :class:`PromptRequest` into provider-ready chat messages."""

    def build(self, request: PromptRequest) -> list[ChatMessage]:
        ...


class DefaultPromptStrategy:
    """System prompt + injected context + windowed history + user turn.

    Injected context is appended to the system message as clearly delimited
    blocks so it cannot masquerade as user/assistant turns.
    """

    def build(self, request: PromptRequest) -> list[ChatMessage]:
        messages: list[ChatMessage] = []

        system_text = (request.system_prompt or "").strip()
        if request.context_blocks:
            rendered = "\n\n".join(
                f"[context:{block.source}]\n{block.content}"
                for block in request.context_blocks
                if block.content.strip()
            )
            if rendered:
                system_text = f"{system_text}\n\n{rendered}" if system_text else rendered
        if system_text:
            messages.append(ChatMessage(role="system", content=system_text))

        window = max(request.context_window, 0)
        history = request.history[-window:] if window else []
        for item in history:
            role = item.role.value if isinstance(item.role, MessageRole) else str(item.role)
            # History system turns are dropped: the agent's system prompt is
            # authoritative and duplicated system messages confuse models.
            if role == MessageRole.SYSTEM.value:
                continue
            messages.append(ChatMessage(role=role, content=item.content))

        if request.user_content:
            messages.append(ChatMessage(role="user", content=request.user_content))
        return messages


class PromptAssembler:
    """Facade the runtime calls; owns the currently-active strategy."""

    def __init__(self, strategy: PromptStrategy | None = None) -> None:
        self._strategy = strategy or DefaultPromptStrategy()

    @property
    def strategy(self) -> PromptStrategy:
        return self._strategy

    def assemble(
        self,
        *,
        system_prompt: str,
        history: list[Message] | None = None,
        user_content: str = "",
        context_blocks: list[ContextBlock] | None = None,
        context_window: int = DEFAULT_CONTEXT_WINDOW,
    ) -> list[ChatMessage]:
        request = PromptRequest(
            system_prompt=system_prompt,
            history=history or [],
            user_content=user_content,
            context_blocks=context_blocks or [],
            context_window=context_window,
        )
        return self._strategy.build(request)
