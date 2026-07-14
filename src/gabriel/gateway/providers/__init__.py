"""LLM provider abstraction: protocol, neutral wire types, registry, Ollama."""
from gabriel.gateway.providers.base import (
    ChatCompletionResult,
    ChatMessage,
    LLMProvider,
    ModelInfo,
    ModelNotFoundError,
    ProviderConnectionError,
    ProviderError,
    ProviderHealth,
    ProviderNotFoundError,
    StreamChunk,
    TokenUsage,
    ToolCallRequest,
)
from gabriel.gateway.providers.ollama import OllamaProvider
from gabriel.gateway.providers.registry import (
    DuplicateProviderError,
    ProviderRegistry,
    provider_registry,
    register_default_providers,
)

__all__ = [
    "ChatCompletionResult",
    "ChatMessage",
    "DuplicateProviderError",
    "LLMProvider",
    "ModelInfo",
    "ModelNotFoundError",
    "OllamaProvider",
    "ProviderConnectionError",
    "ProviderError",
    "ProviderHealth",
    "ProviderNotFoundError",
    "ProviderRegistry",
    "provider_registry",
    "register_default_providers",
    "StreamChunk",
    "TokenUsage",
    "ToolCallRequest",
]
