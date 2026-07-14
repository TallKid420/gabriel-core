"""Embedding providers & registry: Ollama default, hot-swap, failure modes."""
import json

import httpx
import pytest

from gabriel.knowledge.embeddings import (
    DuplicateEmbeddingProviderError,
    EmbeddingConnectionError,
    EmbeddingError,
    EmbeddingProviderRegistry,
    OllamaEmbeddingProvider,
    UnknownEmbeddingProviderError,
    register_default_embedding_providers,
)


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_ollama_embed_batches_texts():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        seen["model"] = payload["model"]
        seen["input"] = payload["input"]
        return httpx.Response(
            200, json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]}
        )

    provider = OllamaEmbeddingProvider(
        model="test-embed", transport=_transport(handler)
    )
    vectors = await provider.embed(["alpha", "beta"])
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert seen["model"] == "test-embed"
    assert seen["input"] == ["alpha", "beta"]


@pytest.mark.asyncio
async def test_ollama_connection_error_is_embedding_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    provider = OllamaEmbeddingProvider(transport=_transport(handler))
    with pytest.raises(EmbeddingConnectionError):
        await provider.embed(["alpha"])


@pytest.mark.asyncio
async def test_ollama_count_mismatch_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [[0.1]]})

    provider = OllamaEmbeddingProvider(transport=_transport(handler))
    with pytest.raises(EmbeddingError):
        await provider.embed(["alpha", "beta"])


def test_registry_register_resolve_and_default():
    registry = EmbeddingProviderRegistry()
    register_default_embedding_providers(registry)
    assert "ollama" in registry.list_providers()
    # Default resolution returns the Ollama provider.
    assert registry.resolve().name == "ollama"
    assert registry.resolve("ollama").name == "ollama"


def test_registry_hot_swap_and_errors():
    registry = EmbeddingProviderRegistry()

    class Custom:
        name = "custom"
        model = "custom-embed"

        async def embed(self, texts):
            return [[0.0] for _ in texts]

    registry.register(Custom())
    assert registry.resolve("custom").model == "custom-embed"
    with pytest.raises(DuplicateEmbeddingProviderError):
        registry.register(Custom())
    with pytest.raises(UnknownEmbeddingProviderError):
        registry.resolve("nope")


def test_register_defaults_is_idempotent():
    registry = EmbeddingProviderRegistry()
    register_default_embedding_providers(registry)
    register_default_embedding_providers(registry)  # no DuplicateError
    assert registry.list_providers().count("ollama") == 1
