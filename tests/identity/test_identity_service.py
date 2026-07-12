"""Unit tests for the IdentityService orchestration layer."""
from __future__ import annotations

import pytest

from gabriel.identity import Capability
from gabriel.identity.auth import InvalidSignatureError
from gabriel.identity.config import IdentitySettings
from gabriel.identity.exceptions import AuthenticationFailedError, ProviderNotFoundError
from gabriel.identity.identity_service import (
    build_default_identity_service,
    build_key_manager,
)


@pytest.fixture
def service():
    # Ephemeral in-process keys; dev provider enabled (non-production).
    return build_default_identity_service(IdentitySettings(environment="test"))


@pytest.mark.asyncio
async def test_login_issues_token_and_session(service):
    result = await service.login("dev", {"userId": "u_alice"})
    assert result.token.value
    assert result.session["authMethod"] == "dev"
    assert result.session["expiresAt"]
    assert result.principal.organization_id == "org_harbor"


@pytest.mark.asyncio
async def test_login_roundtrip_preserves_capabilities(service):
    result = await service.login("dev", {"userId": "u_alice"})

    principal = service.principal_from_token(result.token)
    assert principal.id == result.principal.id
    assert principal.organization_id == "org_harbor"
    # Capabilities survive the JWT round-trip verbatim.
    assert principal.capabilities == result.principal.capabilities
    assert Capability.MANAGE_POLICIES in principal.capabilities


@pytest.mark.asyncio
async def test_login_unknown_method_raises(service):
    with pytest.raises(ProviderNotFoundError):
        await service.login("saml", {"userId": "u_alice"})


@pytest.mark.asyncio
async def test_login_bad_credentials_raises(service):
    with pytest.raises(AuthenticationFailedError):
        await service.login("dev", {"userId": "ghost"})


def test_available_methods_reports_dev(service):
    assert "dev" in service.available_methods()


def test_jwks_exposes_active_key(service):
    jwks = service.jwks()
    assert len(jwks["keys"]) >= 1
    assert jwks["keys"][0]["kid"] == service.key_manager.kid


@pytest.mark.asyncio
async def test_token_from_other_key_is_rejected(service):
    """A token signed by a different KeyManager must not verify."""
    result = await service.login("dev", {"userId": "u_alice"})

    # A fresh service with an independent key set cannot verify the token.
    other = build_default_identity_service(IdentitySettings(environment="test"))
    with pytest.raises(InvalidSignatureError):
        other.principal_from_token(result.token.value)


@pytest.mark.asyncio
async def test_rotation_keeps_existing_tokens_valid(service):
    result = await service.login("dev", {"userId": "u_alice"})
    service.key_manager.rotate()

    # Token signed before rotation still verifies via the retained old key.
    principal = service.principal_from_token(result.token)
    assert principal.organization_id == "org_harbor"


def test_production_disables_dev_provider():
    prod = build_default_identity_service(
        IdentitySettings(environment="production", dev_auth_enabled=False)
    )
    # Dev provider must never register in production; real providers
    # (password, production-token) are the only available methods.
    methods = prod.available_methods()
    assert "dev" not in methods
    assert "password" in methods
    assert "production" in methods
    # JWKS/verification infrastructure still works.
    assert prod.jwks()["keys"]


def test_build_key_manager_loads_from_files(tmp_path):
    km = build_key_manager(IdentitySettings(environment="test"))
    private_path = tmp_path / "priv.pem"
    public_path = tmp_path / "pub.pem"
    km.save_to_files(str(private_path), str(public_path))

    loaded = build_key_manager(
        IdentitySettings(
            environment="test",
            private_key_path=str(private_path),
            public_key_path=str(public_path),
        )
    )
    assert loaded.kid == km.kid
