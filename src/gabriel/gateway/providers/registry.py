"""ProviderRegistry — named lookup of LLM providers.

Mirrors the shape of :class:`gabriel.runtime.registry.RuntimeRegistry` and
:class:`gabriel.tool.registry.FunctionRegistry`: a plain in-process registry
with explicit registration, a module-level default instance, and an
idempotent ``register_default_providers`` bootstrap.

Provider selection is config-driven per agent: the agent's
``model_config.provider`` names the provider; when an agent declares no
provider the registry's ``default_provider`` is used.
"""
from __future__ import annotations

import os

from gabriel.gateway.providers.base import LLMProvider, ProviderNotFoundError


class DuplicateProviderError(Exception):
    """Raised when two providers register under the same name."""


class ProviderRegistry:
    """In-process registry of :class:`LLMProvider` instances keyed by name."""

    def __init__(self, default_provider: str = "ollama") -> None:
        self._providers: dict[str, LLMProvider] = {}
        self.default_provider = default_provider

    def register(self, provider: LLMProvider) -> None:
        if provider.name in self._providers:
            raise DuplicateProviderError(
                f"Provider already registered with name: {provider.name}"
            )
        self._providers[provider.name] = provider

    def get(self, name: str) -> LLMProvider:
        provider = self._providers.get(name)
        if provider is None:
            raise ProviderNotFoundError(
                f"No LLM provider registered with name: '{name}'. "
                f"Available: {sorted(self._providers) or 'none'}"
            )
        return provider

    def resolve(self, name: str | None) -> LLMProvider:
        """Resolve a provider by name, falling back to the default.

        This is the config-driven selection hook: pass the agent's
        ``model_config.provider`` (which may be empty) and get a provider.
        """
        return self.get(name or self.default_provider)

    def is_registered(self, name: str) -> bool:
        return name in self._providers

    def list_providers(self) -> list[str]:
        return sorted(self._providers)

    def all(self) -> dict[str, LLMProvider]:
        return dict(self._providers)

    def __len__(self) -> int:
        return len(self._providers)


# Module-level default registry (tests should build their own instances).
provider_registry = ProviderRegistry()


def register_default_providers(
    registry: ProviderRegistry | None = None,
    *,
    ollama_base_url: str | None = None,
) -> ProviderRegistry:
    """Register built-in providers; safe to call more than once.

    Args:
        registry: Target registry; defaults to the module-level instance.
        ollama_base_url: Override for the Ollama endpoint. Defaults to the
            ``GABRIEL_OLLAMA_BASE_URL`` env var, then ``http://localhost:11434``.
    """
    # NOTE: an explicit ``is None`` check — an empty registry is falsy
    # (``__len__`` == 0) and ``registry or provider_registry`` would silently
    # target the module singleton instead.
    target = registry if registry is not None else provider_registry

    from gabriel.gateway.providers.ollama import OllamaProvider

    base_url = (
        ollama_base_url
        or os.getenv("GABRIEL_OLLAMA_BASE_URL")
        or "http://localhost:11434"
    )
    try:
        target.register(OllamaProvider(base_url=base_url))
    except DuplicateProviderError:
        pass

    return target
