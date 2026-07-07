"""Production JWT identity provider."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gabriel.identity.auth import TokenService
from gabriel.identity.exceptions import AuthenticationFailedError
from gabriel.identity.providers.base import AuthenticationResult, IdentityProvider
from gabriel.identity.repository import PrincipalRepository


class ProductionIdentityProvider(IdentityProvider):
    """Resolve authenticated principals from verified JWT claims."""

    name = "production"

    def __init__(
        self,
        token_service: TokenService,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._token_service = token_service
        self._session_factory = session_factory

    async def authenticate(self, credentials: Mapping[str, Any]) -> AuthenticationResult:
        token = credentials.get("token")
        if not token or not isinstance(token, str):
            raise AuthenticationFailedError("Missing bearer token")

        claims = self._token_service.verify(token)

        async with self._session_factory() as session:
            repo = PrincipalRepository(session)
            principal = await repo.get_by_id(claims.principal_id)

        if principal is None:
            raise AuthenticationFailedError(
                f"Principal '{claims.principal_id}' referenced by token was not found"
            )

        if principal.organization_id != claims.organization_id:
            raise AuthenticationFailedError(
                "Token organization does not match persisted principal organization"
            )

        return AuthenticationResult(principal=principal, session={"authMethod": self.name})