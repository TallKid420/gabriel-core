"""Unit tests for the provider registry and the development identity provider."""
from __future__ import annotations

import pytest

from gabriel.identity import Capability, PrincipalType
from gabriel.identity.config import IdentitySettings
from gabriel.identity.exceptions import (
    AuthenticationFailedError,
    IdentityConfigurationError,
    ProviderNotFoundError,
)
from gabriel.identity.providers.base import AuthenticationResult, IdentityProvider
from gabriel.identity.providers.dev import DevIdentityProvider, capabilities_for_roles
from gabriel.identity.providers.registry import ProviderRegistry


class _StubProvider(IdentityProvider):
    def __init__(self, name: str) -> None:
        self.name = name

    async def authenticate(self, credentials):  # pragma: no cover - not exercised
        raise NotImplementedError


# ── Registry ────────────────────────────────────────────────────────────────


def test_registry_register_and_get():
    registry = ProviderRegistry()
    provider = _StubProvider("password")
    registry.register(provider)

    assert registry.has("password")
    assert registry.get("password") is provider
    assert registry.methods() == ["password"]


def test_registry_rejects_duplicate_registration():
    registry = ProviderRegistry()
    registry.register(_StubProvider("google"))
    with pytest.raises(ValueError):
        registry.register(_StubProvider("google"))


def test_registry_rejects_nameless_provider():
    registry = ProviderRegistry()
    with pytest.raises(ValueError):
        registry.register(_StubProvider(""))


def test_registry_get_unknown_raises():
    registry = ProviderRegistry()
    with pytest.raises(ProviderNotFoundError):
        registry.get("saml")


def test_registry_methods_sorted():
    registry = ProviderRegistry()
    registry.register(_StubProvider("zeta"))
    registry.register(_StubProvider("alpha"))
    assert registry.methods() == ["alpha", "zeta"]


# ── Dev provider: production safety ──────────────────────────────────────────


def test_dev_provider_refuses_production():
    settings = IdentitySettings(environment="production", dev_auth_enabled=True)
    with pytest.raises(IdentityConfigurationError):
        DevIdentityProvider(settings)


def test_dev_provider_refuses_when_disabled():
    settings = IdentitySettings(environment="development", dev_auth_enabled=False)
    with pytest.raises(IdentityConfigurationError):
        DevIdentityProvider(settings)


# ── Dev provider: authentication ─────────────────────────────────────────────


@pytest.fixture
def dev_provider() -> DevIdentityProvider:
    return DevIdentityProvider(IdentitySettings(environment="development"))


@pytest.mark.asyncio
async def test_dev_provider_authenticates_known_user(dev_provider):
    result = await dev_provider.authenticate({"userId": "u_alice"})

    assert isinstance(result, AuthenticationResult)
    principal = result.principal
    assert principal.organization_id == "org_harbor"
    assert principal.principal_type == PrincipalType.USER
    assert principal.display_name == "Alice Nguyen"
    # Workspace admin should carry management capabilities.
    assert Capability.MANAGE_POLICIES in principal.capabilities
    assert Capability.WRITE_RESOURCE in principal.capabilities
    # Session view is provider-populated.
    assert result.session["user"]["id"] == "u_alice"


@pytest.mark.asyncio
async def test_dev_provider_accepts_snake_case_credential(dev_provider):
    result = await dev_provider.authenticate({"user_id": "u_marco"})
    assert result.principal.display_name == "Marco Reyes"


@pytest.mark.asyncio
async def test_dev_provider_unknown_user_fails(dev_provider):
    with pytest.raises(AuthenticationFailedError):
        await dev_provider.authenticate({"userId": "does_not_exist"})


@pytest.mark.asyncio
async def test_dev_provider_missing_credential_fails(dev_provider):
    with pytest.raises(AuthenticationFailedError):
        await dev_provider.authenticate({})


def test_dev_provider_lists_principals(dev_provider):
    principals = dev_provider.list_principals()
    ids = {entry["user"]["id"] for entry in principals}
    assert {"u_alice", "u_marco", "u_sofia", "u_pastor", "u_hamish"} <= ids


# ── Role → capability mapping ────────────────────────────────────────────────


def test_capabilities_for_roles_baseline():
    caps = capabilities_for_roles([])
    assert Capability.AUTHENTICATE in caps
    assert Capability.READ_ORGANIZATION in caps
    # No write/management capabilities without a role.
    assert Capability.WRITE_RESOURCE not in caps
    assert Capability.MANAGE_POLICIES not in caps


def test_capabilities_for_roles_admin_superset_of_member():
    admin = capabilities_for_roles(["workspace_admin"])
    member = capabilities_for_roles(["member"])
    assert member <= admin
    assert Capability.MANAGE_POLICIES in admin
    assert Capability.MANAGE_POLICIES not in member
