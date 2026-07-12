"""Email/password identity provider.

The first *real* authentication method: verifies an email + password against
persisted :class:`~gabriel.user.models.User` records and resolves the mirrored
:class:`~gabriel.identity.principal.Principal` from the database.

Hot-swappable by design (ADR-007): this is just another
:class:`~gabriel.identity.providers.base.IdentityProvider` registered under the
``"password"`` method — swapping to OAuth/SAML/passkeys later means registering
a different provider, with zero changes to the Identity Service or API layer.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gabriel.identity.exceptions import AuthenticationFailedError
from gabriel.identity.providers.base import AuthenticationResult, IdentityProvider
from gabriel.identity.repository import PrincipalRepository
from gabriel.organization.repository import OrganizationRepository
from gabriel.user.models import User
from gabriel.user.service import UserService


def _initials(display_name: str) -> str:
    parts = [p for p in display_name.split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][0].upper()
    return (parts[0][0] + parts[-1][0]).upper()


class PasswordIdentityProvider(IdentityProvider):
    """Authenticates users by email + password stored in the database."""

    name = "password"

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def authenticate(self, credentials: Mapping[str, Any]) -> AuthenticationResult:
        email = credentials.get("email")
        password = credentials.get("password")
        org_id = credentials.get("org_id") or credentials.get("organization_id")
        if not email or not isinstance(email, str):
            raise AuthenticationFailedError("Missing 'email' credential")
        if not password or not isinstance(password, str):
            raise AuthenticationFailedError("Missing 'password' credential")

        async with self._session_factory() as session:
            user_service = UserService(session)
            user = await user_service.authenticate(email, password, org_id=org_id)

            principal = await PrincipalRepository(session).get_by_id(user.principal_id)
            if principal is None:
                raise AuthenticationFailedError(
                    "Authenticated user has no linked principal — contact an administrator"
                )

            org_orm = await OrganizationRepository(session).get_by_org_id(user.org_id)

        org_name = org_orm.display_name if org_orm else user.org_id
        return AuthenticationResult(
            principal=principal,
            session=self._session_view(user, principal.metadata, org_name),
        )

    def _session_view(
        self, user: User, principal_metadata: Mapping[str, Any], org_name: str
    ) -> dict[str, Any]:
        """Build the frontend session view (same shape as the dev provider)."""
        roles = list(principal_metadata.get("roles", []))
        return {
            "user": {
                "id": str(user.grn),
                "principal": user.principal_id,
                "displayName": user.display_name,
                "email": user.email,
                "initials": _initials(user.display_name),
                "avatarUrl": None,
                "roles": roles,
            },
            "organization": {
                "id": user.org_id,
                "name": org_name,
                "slug": user.org_id,
            },
            "tenantId": user.org_id,
            "authMethod": self.name,
        }
