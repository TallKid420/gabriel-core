"""Pluggable authentication providers.

Add a new authentication method by implementing :class:`IdentityProvider` and
registering it with a :class:`ProviderRegistry`. No changes to the Identity
Service or API layer are required.
"""
from gabriel.identity.providers.base import AuthenticationResult, IdentityProvider
from gabriel.identity.providers.dev import DevIdentityProvider
from gabriel.identity.providers.production import ProductionIdentityProvider
from gabriel.identity.providers.registry import ProviderRegistry

__all__ = [
    "AuthenticationResult",
    "IdentityProvider",
    "DevIdentityProvider",
    "ProductionIdentityProvider",
    "ProviderRegistry",
]
