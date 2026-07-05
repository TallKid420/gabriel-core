"""Provider registry.

A minimal, explicit registry mapping a method name (``"dev"``, ``"password"``,
``"google"``, ...) to an :class:`IdentityProvider` instance. Multiple providers
can be registered and are resolved by name at login time, so several
authentication methods can run concurrently.
"""
from __future__ import annotations

from gabriel.identity.exceptions import ProviderNotFoundError
from gabriel.identity.providers.base import IdentityProvider


class ProviderRegistry:
    """Holds the set of active authentication providers, keyed by method name."""

    def __init__(self) -> None:
        self._providers: dict[str, IdentityProvider] = {}

    def register(self, provider: IdentityProvider) -> None:
        """Register a provider under its ``name``.

        Raises:
            ValueError: If the provider has no name or the name is already taken.
        """
        if not provider.name:
            raise ValueError(f"Provider {provider!r} must declare a non-empty name")
        if provider.name in self._providers:
            raise ValueError(f"Provider '{provider.name}' is already registered")
        self._providers[provider.name] = provider

    def get(self, name: str) -> IdentityProvider:
        """Return the provider registered under ``name``.

        Raises:
            ProviderNotFoundError: If no provider is registered for ``name``.
        """
        provider = self._providers.get(name)
        if provider is None:
            available = ", ".join(sorted(self._providers)) or "<none>"
            raise ProviderNotFoundError(
                f"No authentication provider registered for method '{name}'. "
                f"Available: {available}"
            )
        return provider

    def has(self, name: str) -> bool:
        return name in self._providers

    def methods(self) -> list[str]:
        """Return the names of all registered providers."""
        return sorted(self._providers)
