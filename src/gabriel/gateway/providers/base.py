"""LLM provider abstraction (Phase 3 — Gateway AI Runtime).

Every LLM backend (Ollama, OpenAI, Anthropic, …) is exposed to the runtime
through the :class:`LLMProvider` protocol. The runtime never talks to a
vendor SDK directly — it always goes through a provider resolved from the
:class:`~gabriel.gateway.providers.registry.ProviderRegistry`.

Design rules
------------
* Providers are stateless adapters: connection details live on the instance,
  request state travels in arguments.
* All wire formats are normalised to the neutral dataclasses below so the
  rest of the runtime is vendor-agnostic.
* Connection problems surface as :class:`ProviderConnectionError` — the
  runtime converts them into SSE error events instead of crashing streams.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ProviderError(Exception):
    """Base class for all provider failures."""


class ProviderConnectionError(ProviderError):
    """The provider backend is unreachable (network / connection refused)."""


class ProviderNotFoundError(ProviderError):
    """No provider registered under the requested name."""


class ModelNotFoundError(ProviderError):
    """The requested model is not available on the provider backend."""


# ---------------------------------------------------------------------------
# Neutral wire types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChatMessage:
    """A single prompt message in the neutral chat format.

    ``role`` is one of ``system`` / ``user`` / ``assistant`` / ``tool`` and
    maps 1:1 onto :class:`gabriel.conversation.message_models.MessageRole`.
    """

    role: str
    content: str
    name: str | None = None
    tool_call_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name is not None:
            payload["name"] = self.name
        if self.tool_call_id is not None:
            payload["tool_call_id"] = self.tool_call_id
        return payload


@dataclass(frozen=True)
class ToolCallRequest:
    """The model asked the runtime to execute a tool."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TokenUsage:
    """Token accounting for a completion (maps onto Message token fields)."""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True)
class ChatCompletionResult:
    """A full (non-streamed) completion."""

    content: str
    model: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    tool_calls: tuple[ToolCallRequest, ...] = ()
    finish_reason: str = "stop"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StreamChunk:
    """One increment of a streamed completion.

    ``delta`` carries new text; the final chunk has ``done=True`` and carries
    the aggregate ``usage``/``tool_calls`` when the backend reports them.
    """

    delta: str = ""
    done: bool = False
    model: str = ""
    usage: TokenUsage | None = None
    tool_calls: tuple[ToolCallRequest, ...] = ()
    finish_reason: str | None = None


@dataclass(frozen=True)
class ModelInfo:
    """A model available on a provider backend."""

    name: str
    provider: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderHealth:
    """Result of a provider health probe."""

    provider: str
    healthy: bool
    detail: str = ""


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMProvider(Protocol):
    """Contract every LLM provider must implement.

    Concrete providers (OllamaProvider today; OpenAI/Anthropic later) are
    registered by ``name`` in the ProviderRegistry and resolved per agent via
    the agent's ``model_config.provider`` field.
    """

    @property
    def name(self) -> str:
        """Unique registry key, e.g. ``"ollama"``."""
        ...

    async def chat_completion(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
    ) -> ChatCompletionResult:
        """Return a complete (non-streamed) chat completion."""
        ...

    def stream_chat_completion(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Yield :class:`StreamChunk` increments (async generator)."""
        ...

    async def list_models(self) -> list[ModelInfo]:
        """Return the models available on this provider backend."""
        ...

    async def health_check(self) -> ProviderHealth:
        """Probe the backend; never raises — reports via ProviderHealth."""
        ...
