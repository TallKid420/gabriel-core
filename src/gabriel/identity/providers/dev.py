"""Development identity provider.

A simplified provider for local development and tests. It authenticates against
a small set of hardcoded principals — no passwords, no external IdP. It exists
so the platform is usable end-to-end before real providers (password, OAuth,
SAML, passkeys) land.

Production safety
-----------------
This provider is a deliberate authentication bypass and MUST NEVER run in
production. It fails loudly at construction time when ``settings.is_production``
is true (or when explicitly disabled), so a misconfigured deployment crashes on
startup rather than silently accepting fake identities.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from gabriel.identity.config import IdentitySettings
from gabriel.identity.exceptions import (
    AuthenticationFailedError,
    IdentityConfigurationError,
)
from gabriel.identity.models import Capability, PrincipalStatus, PrincipalType
from gabriel.identity.principal import Principal
from gabriel.identity.principal_id import PrincipalID
from gabriel.identity.providers.base import AuthenticationResult, IdentityProvider


ORGANIZATIONS = [
    {"id": "org_harbor", "name": "Harbor Mutual Insurance", "plan": "Pilot"},
    {"id": "org_thread", "name": "Thread & Needle Custom Clothing", "plan": "Pilot"},
    {"id": "org_grace", "name": "Grace Community Church", "plan": "Pilot"},
    {"id": "org_highland", "name": "Highland Bagpiping Co.", "plan": "Pilot"},
]

DEV_PRINCIPALS = [
    {
        "organization": ORGANIZATIONS[0],
        "roles": ["workspace_admin"],
        "user": {
            "id": "u_alice",
            "displayName": "Alice Nguyen",
            "principal": "principal://org_harbor/user/alice",
            "email": "alice@harbormutual.com",
        },
    },
    {
        "organization": ORGANIZATIONS[0],
        "roles": ["member"],
        "user": {
            "id": "u_marco",
            "displayName": "Marco Reyes",
            "principal": "principal://org_harbor/user/marco",
            "email": "marco@harbormutual.com",
        },
    },
    {
        "organization": ORGANIZATIONS[1],
        "roles": ["workspace_admin"],
        "user": {
            "id": "u_sofia",
            "displayName": "Sofia Bianchi",
            "principal": "principal://org_thread/user/sofia",
            "email": "sofia@threadandneedle.com",
        },
    },
    {
        "organization": ORGANIZATIONS[2],
        "roles": ["workspace_admin"],
        "user": {
            "id": "u_pastor",
            "displayName": "Pastor David Kim",
            "principal": "principal://org_grace/user/david",
            "email": "david@gracecommunity.org",
        },
    },
    {
        "organization": ORGANIZATIONS[3],
        "roles": ["workspace_admin", "operator"],
        "user": {
            "id": "u_hamish",
            "displayName": "Hamish MacLeod",
            "principal": "principal://org_highland/user/hamish",
            "email": "hamish@highlandpipes.co",
        },
    },
]


def capabilities_for_roles(roles: list[str]) -> set[Capability]:
    """Map coarse workspace roles to Gabriel capabilities.

    Capabilities are what a principal is *capable* of; PEEL decides what they are
    *allowed* to do. Every authenticated principal can at least authenticate and
    read its organization.
    """
    capabilities: set[Capability] = {
        Capability.AUTHENTICATE,
        Capability.READ_ORGANIZATION,
        Capability.READ_PRINCIPAL,
    }
    role_set = set(roles)

    if "workspace_admin" in role_set:
        capabilities.update(
            {
                Capability.READ_RESOURCE,
                Capability.WRITE_RESOURCE,
                Capability.EXECUTE_WORKFLOW,
                Capability.CALL_TOOL,
                Capability.MANAGE_PRINCIPALS,
                Capability.MANAGE_POLICIES,
            }
        )
    if "member" in role_set:
        capabilities.update(
            {
                Capability.READ_RESOURCE,
                Capability.WRITE_RESOURCE,
                Capability.EXECUTE_WORKFLOW,
            }
        )
    if "operator" in role_set:
        capabilities.update(
            {
                Capability.READ_RESOURCE,
                Capability.WRITE_RESOURCE,
                Capability.EXECUTE_WORKFLOW,
                Capability.CALL_TOOL,
            }
        )
    return capabilities


class DevIdentityProvider(IdentityProvider):
    """Authenticates hardcoded development principals by ``userId``."""

    name = "dev"

    def __init__(self, settings: IdentitySettings) -> None:
        if settings.is_production:
            raise IdentityConfigurationError(
                "DevIdentityProvider must not be used in production "
                "(GABRIEL_ENV=production). Configure a real authentication provider."
            )
        if not settings.dev_auth_enabled:
            raise IdentityConfigurationError(
                "DevIdentityProvider is disabled (GABRIEL_DEV_AUTH_ENABLED=false)."
            )
        self._settings = settings
        self._by_user_id = {entry["user"]["id"]: entry for entry in DEV_PRINCIPALS}

    def list_principals(self) -> list[dict[str, Any]]:
        """Return the catalogue of dev principals (for the login picker UI)."""
        return DEV_PRINCIPALS

    async def authenticate(self, credentials: Mapping[str, Any]) -> AuthenticationResult:
        user_id = credentials.get("userId") or credentials.get("user_id")
        if not user_id:
            raise AuthenticationFailedError("Missing 'userId' credential for dev login")

        entry = self._by_user_id.get(user_id)
        if entry is None:
            raise AuthenticationFailedError(f"Unknown dev principal '{user_id}'")

        user = entry["user"]
        organization = entry["organization"]
        roles = entry.get("roles", [])

        principal_id = PrincipalID.parse(user["principal"])
        principal = Principal(
            id=principal_id,
            organization_id=principal_id.org_id,
            principal_type=PrincipalType.USER,
            display_name=user["displayName"],
            status=PrincipalStatus.ACTIVE,
            capabilities=capabilities_for_roles(roles),
            metadata={
                "email": user["email"],
                "roles": roles,
                "auth_method": self.name,
                "user_id": user["id"],
            },
        )

        session = {
            "user": {
                "id": user["id"],
                "principal": user["principal"],
                "displayName": user["displayName"],
                "email": user["email"],
                "initials": user["displayName"][0].upper(),
                "avatarUrl": None,
                "roles": roles,
            },
            "organization": {
                "id": organization["id"],
                "name": organization["name"],
                "slug": organization["id"],
            },
            "tenantId": organization["id"],
            "authMethod": self.name,
        }
        return AuthenticationResult(principal=principal, session=session)
