from __future__ import annotations

from dataclasses import dataclass
from pydantic import BaseModel

from fastapi import Response, Request, HTTPException, Header

from gabriel.api.errors import AuthenticationError
from gabriel.identity.models import Capability, PrincipalStatus, PrincipalType
from gabriel.identity.principal import Principal
from gabriel.identity.principal_id import PrincipalID


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

# ── Dev Identity Provider ──────────────────────────────────────────────────

DEV_PRINCIPALS = [
    {
        "userId": "user_insurance_alice",
        "displayName": "Alice Chen",
        "email": "alice@acme-insurance.example",
        "orgId": "org_insurance",
        "orgName": "Acme Insurance",
        "roles": ["admin"],
        "principal": "principal://org_insurance/user/alice",
    },
    {
        "userId": "user_clothing_bob",
        "displayName": "Bob Kim",
        "email": "bob@custom-clothing.example",
        "orgId": "org_clothing",
        "orgName": "Custom Clothing Co",
        "roles": ["member"],
        "principal": "principal://org_clothing/user/bob",
    },
]

class DevLoginRequest(BaseModel):
    userId: str

async def dev_login(body: DevLoginRequest, response: Response):
    match = next((p for p in DEV_PRINCIPALS if p["userId"] == body.userId), None)
    if not match:
        raise HTTPException(status_code=404, detail="Unknown dev principal")

    # Build a session view — same shape the frontend Session type expects
    session = {
        "user": {
            "id": match["userId"],
            "principal": match["principal"],
            "displayName": match["displayName"],
            "email": match["email"],
            "initials": match["displayName"][0].upper(),
            "avatarUrl": None,
            "roles": match["roles"],
        },
        "organization": {
            "id": match["orgId"],
            "name": match["orgName"],
            "slug": match["orgId"],
        },
        "tenantId": match["orgId"],
        "authMethod": "dev",
        "expiresAt": "2099-01-01T00:00:00Z",
        # The principal token — Gateway will use this in Authorization header
        # when calling Core on behalf of the user
        "_principalToken": match["principal"],
    }

    # Set httpOnly cookie so the browser never sees the token
    response.set_cookie(
        key="gabriel_session",
        value=match["principal"],
        httponly=True,
        samesite="lax",
        max_age=8 * 60 * 60,
    )
    return session

async def get_session(request: Request):
    token = request.cookies.get("gabriel_session")
    if not token:
        raise HTTPException(status_code=401, detail="No session")

    # Find matching principal
    principal_str = token
    match = next(
        (p for p in DEV_PRINCIPALS if p["principal"] == principal_str), None
    )
    if not match:
        raise HTTPException(status_code=401, detail="Invalid session")

    return {
        "user": {
            "id": match["userId"],
            "principal": match["principal"],
            "displayName": match["displayName"],
            "email": match["email"],
            "initials": match["displayName"][0].upper(),
            "avatarUrl": None,
            "roles": match["roles"],
        },
        "organization": {
            "id": match["orgId"],
            "name": match["orgName"],
            "slug": match["orgId"],
        },
        "tenantId": match["orgId"],
        "authMethod": "dev",
        "expiresAt": "2099-01-01T00:00:00Z",
    }