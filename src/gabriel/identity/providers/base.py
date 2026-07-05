"""Authentication provider interface.

An :class:`IdentityProvider` turns externally-supplied credentials into a
verified :class:`~gabriel.identity.principal.Principal`. Providers are the sole
extension point for adding new authentication methods (email/password, Google
OAuth, Microsoft Entra ID, Okta, SAML, passkeys, ...) without touching the
Identity Service or API layer — a new method is a new provider registered under
its ``name``.

Design notes
------------
* Providers only *authenticate* (prove who you are). They do not issue tokens or
  evaluate authorization — that separation is mandated by ADR-007.
* ``authenticate`` returns an :class:`AuthenticationResult` wrapping the verified
  principal plus optional provider-specific session metadata (e.g. the frontend
  session view). Keeping the return type richer than a bare ``Principal`` means
  future providers (OAuth profile data, SAML attributes) need no signature change.
"""
from __future__ import annotations

import abc
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from gabriel.identity.principal import Principal


@dataclass(frozen=True)
class AuthenticationResult:
    """The outcome of a successful authentication.

    Attributes:
        principal: The verified principal (identity + capabilities).
        session: Optional provider-specific session view. The development
            provider populates this with the shape the frontend expects; other
            providers may leave it empty.
    """

    principal: Principal
    session: dict[str, Any] = field(default_factory=dict)


class IdentityProvider(abc.ABC):
    """Base class for all authentication providers.

    Subclasses declare a unique :attr:`name` (the ``method`` selector used at
    login) and implement :meth:`authenticate`.
    """

    #: Unique method identifier, e.g. ``"dev"``, ``"password"``, ``"google"``.
    name: str = ""

    @abc.abstractmethod
    async def authenticate(self, credentials: Mapping[str, Any]) -> AuthenticationResult:
        """Verify ``credentials`` and return the authenticated principal.

        Args:
            credentials: Method-specific credential payload from the login request.

        Returns:
            AuthenticationResult: The verified principal and optional session view.

        Raises:
            gabriel.identity.exceptions.AuthenticationFailedError: If the
                credentials are invalid or the principal cannot be authenticated.
        """
        raise NotImplementedError
