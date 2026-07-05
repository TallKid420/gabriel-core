from __future__ import annotations

from collections.abc import Iterable

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from gabriel.api.app import create_app
from gabriel.identity import Capability, Principal, PrincipalID, PrincipalType


@pytest.fixture(scope="session", autouse=True)
def _shared_signing_keys(tmp_path_factory) -> None:
    """Persist a single RSA keypair on disk for the whole test session.

    ``create_app`` builds a fresh IdentityService per app instance. Without a
    shared key the JWT minted for one app would not verify against another
    (e.g. the app-restart test), so we point every instance at the same PEM
    files via the standard configuration env vars. This mirrors production,
    where keys are mounted rather than generated per process.
    """
    key_dir = tmp_path_factory.mktemp("jwt-keys")
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_path = key_dir / "private.pem"
    public_path = key_dir / "public.pem"
    private_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    import os

    os.environ["GABRIEL_JWT_PRIVATE_KEY_PATH"] = str(private_path)
    os.environ["GABRIEL_JWT_PUBLIC_KEY_PATH"] = str(public_path)
    yield
    os.environ.pop("GABRIEL_JWT_PRIVATE_KEY_PATH", None)
    os.environ.pop("GABRIEL_JWT_PUBLIC_KEY_PATH", None)

# Capability set mirroring a workspace admin — broad enough for API tests.
ADMIN_CAPABILITIES = (
    "authenticate",
    "read_organization",
    "read_principal",
    "read_resource",
    "write_resource",
    "execute_workflow",
    "call_tool",
    "manage_principals",
    "manage_policies",
)


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def issue_token_headers(
    client: TestClient,
    *,
    org: str = "acme",
    identifier: str = "alice",
    principal_type: str = "user",
    capabilities: Iterable[str] = ADMIN_CAPABILITIES,
    correlation_id: str | None = "11111111-1111-1111-1111-111111111111",
) -> dict[str, str]:
    """Mint a real signed JWT for a synthetic principal and return auth headers.

    Uses the running app's IdentityService so the middleware verifies against the
    same signing key.
    """
    identity_service = client.app.state.identity_service
    principal = Principal(
        id=PrincipalID(org_id=org, principal_type=principal_type, principal_identifier=identifier),
        organization_id=org,
        principal_type=PrincipalType(principal_type),
        display_name=identifier,
        capabilities={Capability(cap) for cap in capabilities},
    )
    token = identity_service.token_service.issue(principal)
    headers = {"Authorization": f"Bearer {token.value}"}
    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id
    return headers


@pytest.fixture
def make_auth_headers(client: TestClient):
    """Factory fixture to build auth headers for arbitrary principals/capabilities."""

    def _make(**kwargs) -> dict[str, str]:
        return issue_token_headers(client, **kwargs)

    return _make


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    """Auth headers for a broadly-capable admin principal in org 'acme'."""
    return issue_token_headers(client)
