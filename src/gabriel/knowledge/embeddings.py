"""Embedding provider abstraction (Phase 4 — Document & Knowledge).

Mirrors the Phase-3 LLM provider design: a small protocol, a concrete Ollama
implementation, and a named registry so alternative providers (OpenAI, …) can
be hot-swapped without touching the pipeline.

Ollama endpoint: ``POST /api/embed`` with ``{"model": ..., "input": [...]}``
returning ``{"embeddings": [[...], ...]}`` (batch-capable, Ollama >= 0.1.34).
Connection failures raise :class:`EmbeddingConnectionError` so callers can
degrade gracefully (store chunks without embeddings, fall back to keyword
search).
"""
from __future__ import annotations

import os
from typing import Any, Protocol, runtime_checkable

import httpx

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
# nomic-embed-text produces 768-dim vectors; keep in sync with the migration.
DEFAULT_EMBEDDING_DIMENSIONS = 768


class EmbeddingError(Exception):
    """Base class for embedding failures."""


class EmbeddingConnectionError(EmbeddingError):
    """The embedding backend is unreachable."""


class UnknownEmbeddingProviderError(EmbeddingError):
    """Requested provider name is not registered."""


class DuplicateEmbeddingProviderError(EmbeddingError):
    """A provider with the same name is already registered."""


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Generates dense vector embeddings for text."""

    @property
    def name(self) -> str:
        ...

    @property
    def model(self) -> str:
        ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed *texts*, returning one vector per input (order preserved)."""
        ...


class OllamaEmbeddingProvider:
    """Default embedding provider backed by Ollama's ``/api/embed``."""

    def __init__(
        self,
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        *,
        model: str = DEFAULT_EMBEDDING_MODEL,
        timeout_seconds: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds
        # Injectable transport keeps the provider testable without a daemon.
        self._transport = transport

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def model(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload: dict[str, Any] = {"model": self._model, "input": texts}
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = await client.post("/api/embed", json=payload)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
            raise EmbeddingConnectionError(
                f"Cannot reach Ollama at {self._base_url}: {exc}"
            ) from exc

        if response.status_code >= 400:
            detail = ""
            try:
                detail = response.json().get("error", "")
            except ValueError:
                detail = response.text[:200]
            raise EmbeddingError(
                f"Ollama embed failed with HTTP {response.status_code}: {detail}"
            )

        embeddings = response.json().get("embeddings") or []
        if len(embeddings) != len(texts):
            raise EmbeddingError(
                f"Ollama returned {len(embeddings)} embeddings for "
                f"{len(texts)} inputs"
            )
        return [[float(x) for x in vector] for vector in embeddings]


class EmbeddingProviderRegistry:
    """Named registry of embedding providers (default: ``ollama``)."""

    def __init__(self, default_provider: str = "ollama") -> None:
        self._providers: dict[str, EmbeddingProvider] = {}
        self._default = default_provider

    @property
    def default_provider(self) -> str:
        return self._default

    def register(self, provider: EmbeddingProvider, *, default: bool = False) -> None:
        if provider.name in self._providers:
            raise DuplicateEmbeddingProviderError(
                f"Embedding provider '{provider.name}' is already registered"
            )
        self._providers[provider.name] = provider
        if default:
            self._default = provider.name

    def get(self, name: str) -> EmbeddingProvider:
        try:
            return self._providers[name]
        except KeyError as exc:
            raise UnknownEmbeddingProviderError(
                f"Embedding provider '{name}' is not registered"
            ) from exc

    def resolve(self, name: str | None = None) -> EmbeddingProvider:
        """Return the named provider, or the default when *name* is falsy."""
        return self.get(name or self._default)

    def list_providers(self) -> list[str]:
        return sorted(self._providers)


def register_default_embedding_providers(
    registry: EmbeddingProviderRegistry,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    """Register the built-in Ollama embedding provider (idempotent)."""
    if "ollama" in registry.list_providers():
        return
    base_url = os.environ.get("GABRIEL_OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL)
    model = os.environ.get("GABRIEL_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    registry.register(
        OllamaEmbeddingProvider(base_url, model=model, transport=transport)
    )
