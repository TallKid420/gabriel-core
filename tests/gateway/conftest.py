"""Fixtures for Gateway AI Runtime tests (Phase 3)."""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gabriel.database.base import Base
from gabriel.gateway.providers.base import (
    ChatCompletionResult,
    ChatMessage,
    ModelInfo,
    ProviderHealth,
    StreamChunk,
    TokenUsage,
    ToolCallRequest,
)

# Import all ORM models to register them with Base.metadata
import gabriel.events.orm  # noqa: F401
import gabriel.agent.orm  # noqa: F401
import gabriel.conversation.orm  # noqa: F401
import gabriel.conversation.message_orm  # noqa: F401
import gabriel.tool.orm  # noqa: F401

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


class FakeProvider:
    """Scriptable in-memory LLMProvider for tests.

    ``script`` is a list of *iterations*; each iteration is a dict with:
        text:       str — streamed in two chunks;
        tool_calls: list[ToolCallRequest] — attached to the final chunk.
    Each ``stream_chat_completion`` call consumes the next iteration.
    """

    def __init__(self, script: list[dict[str, Any]] | None = None, name: str = "fake"):
        self._name = name
        self.script = script or [{"text": "Hello from fake"}]
        self.calls: list[dict[str, Any]] = []
        self._iteration = 0

    @property
    def name(self) -> str:
        return self._name

    def _next(self) -> dict[str, Any]:
        step = self.script[min(self._iteration, len(self.script) - 1)]
        self._iteration += 1
        return step

    async def chat_completion(
        self, messages: list[ChatMessage], *, model: str, **kwargs: Any
    ) -> ChatCompletionResult:
        self.calls.append({"messages": list(messages), "model": model, **kwargs})
        step = self._next()
        return ChatCompletionResult(
            content=step.get("text", ""),
            model=model,
            usage=TokenUsage(prompt_tokens=7, completion_tokens=5),
            tool_calls=tuple(step.get("tool_calls", ())),
        )

    async def stream_chat_completion(
        self, messages: list[ChatMessage], *, model: str, **kwargs: Any
    ) -> AsyncIterator[StreamChunk]:
        self.calls.append({"messages": list(messages), "model": model, **kwargs})
        step = self._next()
        text = step.get("text", "")
        half = max(len(text) // 2, 1)
        if text:
            yield StreamChunk(delta=text[:half], model=model)
            if text[half:]:
                yield StreamChunk(delta=text[half:], model=model)
        yield StreamChunk(
            done=True,
            model=model,
            usage=TokenUsage(prompt_tokens=7, completion_tokens=5),
            tool_calls=tuple(step.get("tool_calls", ())),
            finish_reason="stop",
        )

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(name="fake-model", provider=self._name)]

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider=self._name, healthy=True, detail="fake ok")


def make_tool_call(name: str, call_id: str = "call-1", **arguments: Any) -> ToolCallRequest:
    return ToolCallRequest(id=call_id, name=name, arguments=arguments)
