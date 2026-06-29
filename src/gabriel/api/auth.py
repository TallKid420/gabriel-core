from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header

from gabriel.identity.models import Capability, PrincipalStatus, PrincipalType
from gabriel.identity.principal import Principal
from gabriel.identity.principal_id import PrincipalID


class AuthenticationError(Exception):
	pass


@dataclass(frozen=True)
class AuthenticatedPrincipal:
	principal: Principal
	token: str


def _parse_principal_type(raw_type: str) -> PrincipalType:
	try:
		return PrincipalType(raw_type)
	except ValueError as exc:
		raise AuthenticationError(f"Unsupported principal type '{raw_type}'") from exc


def _parse_capabilities(raw_capabilities: str | None) -> set[Capability]:
	if not raw_capabilities:
		return set()

	capabilities: set[Capability] = set()
	for item in raw_capabilities.split(","):
		value = item.strip()
		if not value:
			continue
		try:
			capabilities.add(Capability(value))
		except ValueError as exc:
			raise AuthenticationError(f"Unknown capability '{value}'") from exc
	return capabilities


def authenticate_bearer_token(
	authorization: str | None = Header(default=None),
	x_capabilities: str | None = Header(default=None),
	x_principal_name: str | None = Header(default=None),
) -> AuthenticatedPrincipal:
	if not authorization:
		raise AuthenticationError("Missing Authorization header")

	if not authorization.lower().startswith("bearer "):
		raise AuthenticationError("Authorization header must use Bearer token")

	token = authorization.split(" ", 1)[1].strip()
	if not token:
		raise AuthenticationError("Bearer token is empty")

	if not token.startswith("principal://"):
		raise AuthenticationError("Only principal:// tokens are supported in this milestone")

	principal_id = PrincipalID.parse(token)
	principal_type = _parse_principal_type(principal_id.principal_type)
	principal = Principal(
		id=principal_id,
		organization_id=principal_id.org_id,
		principal_type=principal_type,
		display_name=x_principal_name or principal_id.principal_identifier,
		status=PrincipalStatus.ACTIVE,
		capabilities=_parse_capabilities(x_capabilities),
	)

	return AuthenticatedPrincipal(principal=principal, token=token)

