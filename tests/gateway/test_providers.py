"""ProviderRegistry + Ollama provider tests (Phase 3)."""
from __future__ import annotations

import json

import httpx
import pytest

from gabriel.gateway.providers.base import (
    ChatMessage,
    ProviderConnectionError,
    ProviderError,
    ProviderNotFoundError,
)
from gabriel.gateway.providers.ollama import OllamaProvider
from gabriel.gateway.providers.registry import (
    DuplicateProviderError,
    ProviderRegistry,
    register_default_providers,
)

from tests.gateway.conftest import FakeProvider


# ── ProviderRegistry ─────────────────────────────────────────────────────────


def test_register_and_get():
    registry = ProviderRegistry()
    provider = FakeProvider()
    registry.register(provider)
    assert registry.get("fake") is provider
    assert registry.is_registered("fake")
    assert registry.list_providers() == ["fake"]


def test_duplicate_registration_rejected():
    registry = ProviderRegistry()
    registry.register(FakeProvider())
    with pytest.raises(DuplicateProviderError):
        registry.register(FakeProvider())


def test_unknown_provider_raises():
    with pytest.raises(ProviderNotFoundError):
        ProviderRegistry().get("nope")


def test_resolve_falls_back_to_default():
    registry = ProviderRegistry(default_provider="fake")
    provider = FakeProvider()
    registry.register(provider)
    assert registry.resolve(None) is provider
    assert registry.resolve("") is provider
    assert registry.resolve("fake") is provider


def test_register_default_providers_registers_ollama_idempotently():
    registry = ProviderRegistry()
    register_default_providers(registry, ollama_base_url="http://example:11434")
    register_default_providers(registry)  # idempotent
    assert registry.list_providers() == ["ollama"]
    assert registry.get("ollama").base_url == "http://example:11434"


# ── OllamaProvider (httpx.MockTransport — no daemon required) ───────────────


def _ollama(handler) -> OllamaProvider:
    return OllamaProvider(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_chat_completion_parses_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        body = json.loads(request.content)
        assert body["stream"] is False
        assert body["options"]["temperature"] == 0.5
        assert body["options"]["num_predict"] == 64
        return httpx.Response(
            200,
            json={
                "model": "llama3",
                "message": {"role": "assistant", "content": "Hi there"},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 11,
                "eval_count": 4,
            },
        )

    result = await _ollama(handler).chat_completion(
        [ChatMessage(role="user", content="Hi")],
        model="llama3",
        temperature=0.5,
        max_tokens=64,
    )
    assert result.content == "Hi there"
    assert result.usage.prompt_tokens == 11
    assert result.usage.completion_tokens == 4
    assert result.usage.total_tokens == 15
    assert result.finish_reason == "stop"


@pytest.mark.asyncio
async def test_stream_chat_completion_yields_chunks():
    lines = [
        {"model": "llama3", "message": {"content": "Hel"}, "done": False},
        {"model": "llama3", "message": {"content": "lo"}, "done": False},
        {
            "model": "llama3",
            "message": {"content": ""},
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 9,
            "eval_count": 2,
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        payload = "\n".join(json.dumps(line) for line in lines)
        return httpx.Response(200, content=payload.encode())

    chunks = [
        c
        async for c in _ollama(handler).stream_chat_completion(
            [ChatMessage(role="user", content="Hi")], model="llama3"
        )
    ]
    assert "".join(c.delta for c in chunks) == "Hello"
    assert chunks[-1].done is True
    assert chunks[-1].usage.total_tokens == 11
    assert chunks[-1].finish_reason == "stop"


@pytest.mark.asyncio
async def test_chat_completion_parses_tool_calls():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "llama3",
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "current_datetime",
                                "arguments": {"timezone": "utc"},
                            }
                        }
                    ],
                },
                "done": True,
            },
        )

    result = await _ollama(handler).chat_completion(
        [ChatMessage(role="user", content="What time is it?")], model="llama3"
    )
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "current_datetime"
    assert result.tool_calls[0].arguments == {"timezone": "utc"}


@pytest.mark.asyncio
async def test_list_models():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(
            200,
            json={"models": [{"name": "llama3:8b", "size": 123, "details": {}}]},
        )

    models = await _ollama(handler).list_models()
    assert [m.name for m in models] == ["llama3:8b"]
    assert models[0].provider == "ollama"


@pytest.mark.asyncio
async def test_connection_error_is_wrapped():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    provider = _ollama(handler)
    with pytest.raises(ProviderConnectionError):
        await provider.chat_completion(
            [ChatMessage(role="user", content="Hi")], model="llama3"
        )
    with pytest.raises(ProviderConnectionError):
        await provider.list_models()
    with pytest.raises(ProviderConnectionError):
        async for _ in provider.stream_chat_completion(
            [ChatMessage(role="user", content="Hi")], model="llama3"
        ):
            pass


@pytest.mark.asyncio
async def test_health_check_never_raises():
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    health = await _ollama(down).health_check()
    assert health.healthy is False
    assert "Cannot reach" in health.detail

    def up(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"version": "0.5.0"})

    health = await _ollama(up).health_check()
    assert health.healthy is True
    assert "0.5.0" in health.detail


@pytest.mark.asyncio
async def test_http_error_surfaces_as_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    with pytest.raises(ProviderError, match="boom"):
        await _ollama(handler).chat_completion(
            [ChatMessage(role="user", content="Hi")], model="llama3"
        )
