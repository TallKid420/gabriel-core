"""Ollama provider — first concrete :class:`LLMProvider` implementation.

Talks to a local Ollama daemon (default ``http://localhost:11434``) using its
native HTTP API:

* ``POST /api/chat``   — chat completion (``stream`` true/false)
* ``GET  /api/tags``   — installed model listing
* ``GET  /api/version``— health probe

Connection failures are wrapped in :class:`ProviderConnectionError` so the
runtime can degrade gracefully (SSE error event instead of a 500).
"""
from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx

from gabriel.gateway.providers.base import (
    ChatCompletionResult,
    ChatMessage,
    ModelInfo,
    ModelNotFoundError,
    ProviderConnectionError,
    ProviderError,
    ProviderHealth,
    StreamChunk,
    TokenUsage,
    ToolCallRequest,
)

DEFAULT_BASE_URL = "http://localhost:11434"


def _parse_tool_calls(message: dict[str, Any]) -> tuple[ToolCallRequest, ...]:
    """Normalise Ollama tool_calls into neutral ToolCallRequest objects."""
    calls: list[ToolCallRequest] = []
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        arguments = function.get("arguments") or {}
        if isinstance(arguments, str):  # some backends serialise arguments
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {"__raw__": arguments}
        calls.append(
            ToolCallRequest(
                id=str(call.get("id") or uuid.uuid4()),
                name=function.get("name", ""),
                arguments=arguments,
            )
        )
    return tuple(calls)


def _usage_from(payload: dict[str, Any]) -> TokenUsage:
    return TokenUsage(
        prompt_tokens=int(payload.get("prompt_eval_count") or 0),
        completion_tokens=int(payload.get("eval_count") or 0),
    )


class OllamaProvider:
    """LLMProvider adapter for the Ollama HTTP API."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout_seconds: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        # Injectable transport keeps the provider testable without a daemon.
        self._transport = transport

    # ------------------------------------------------------------------
    # LLMProvider protocol
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def base_url(self) -> str:
        return self._base_url

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            transport=self._transport,
        )

    def _chat_payload(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float,
        max_tokens: int | None,
        tools: list[dict[str, Any]] | None,
        options: dict[str, Any] | None,
        stream: bool,
    ) -> dict[str, Any]:
        if not model:
            raise ProviderError("Ollama chat requires a model name")
        ollama_options: dict[str, Any] = {"temperature": temperature}
        if max_tokens is not None:
            ollama_options["num_predict"] = max_tokens
        if options:
            ollama_options.update(options)
        payload: dict[str, Any] = {
            "model": model,
            "messages": [m.to_dict() for m in messages],
            "stream": stream,
            "options": ollama_options,
        }
        if tools:
            payload["tools"] = tools
        return payload

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
        payload = self._chat_payload(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            options=options,
            stream=False,
        )
        try:
            async with self._client() as client:
                response = await client.post("/api/chat", json=payload)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
            raise ProviderConnectionError(
                f"Cannot reach Ollama at {self._base_url}: {exc}"
            ) from exc
        self._raise_for_status(response, model)
        data = response.json()
        message = data.get("message") or {}
        return ChatCompletionResult(
            content=message.get("content", ""),
            model=data.get("model", model),
            usage=_usage_from(data),
            tool_calls=_parse_tool_calls(message),
            finish_reason=data.get("done_reason") or "stop",
            raw=data,
        )

    async def stream_chat_completion(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        payload = self._chat_payload(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            options=options,
            stream=True,
        )
        try:
            async with self._client() as client:
                async with client.stream("POST", "/api/chat", json=payload) as response:
                    if response.status_code >= 400:
                        await response.aread()
                        self._raise_for_status(response, model)
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue  # skip malformed keep-alive lines
                        message = data.get("message") or {}
                        done = bool(data.get("done"))
                        yield StreamChunk(
                            delta=message.get("content", ""),
                            done=done,
                            model=data.get("model", model),
                            usage=_usage_from(data) if done else None,
                            tool_calls=_parse_tool_calls(message),
                            finish_reason=data.get("done_reason") if done else None,
                        )
                        if done:
                            return
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
            raise ProviderConnectionError(
                f"Cannot reach Ollama at {self._base_url}: {exc}"
            ) from exc

    async def list_models(self) -> list[ModelInfo]:
        try:
            async with self._client() as client:
                response = await client.get("/api/tags")
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
            raise ProviderConnectionError(
                f"Cannot reach Ollama at {self._base_url}: {exc}"
            ) from exc
        self._raise_for_status(response, model=None)
        models = response.json().get("models") or []
        return [
            ModelInfo(
                name=item.get("name", ""),
                provider=self.name,
                metadata={
                    "size": item.get("size"),
                    "modified_at": item.get("modified_at"),
                    "details": item.get("details", {}),
                },
            )
            for item in models
        ]

    async def health_check(self) -> ProviderHealth:
        try:
            async with self._client() as client:
                response = await client.get("/api/version")
            if response.status_code == 200:
                version = response.json().get("version", "unknown")
                return ProviderHealth(
                    provider=self.name,
                    healthy=True,
                    detail=f"ollama {version} at {self._base_url}",
                )
            return ProviderHealth(
                provider=self.name,
                healthy=False,
                detail=f"HTTP {response.status_code} from {self._base_url}",
            )
        except httpx.HTTPError as exc:
            return ProviderHealth(
                provider=self.name,
                healthy=False,
                detail=f"Cannot reach Ollama at {self._base_url}: {exc}",
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _raise_for_status(self, response: httpx.Response, model: str | None) -> None:
        if response.status_code < 400:
            return
        detail = ""
        try:
            detail = response.json().get("error", "")
        except (json.JSONDecodeError, ValueError):
            detail = response.text[:200]
        if response.status_code == 404 and model and "not found" in detail.lower():
            raise ModelNotFoundError(
                f"Model '{model}' is not available on Ollama ({detail})"
            )
        raise ProviderError(
            f"Ollama request failed with HTTP {response.status_code}: {detail}"
        )
