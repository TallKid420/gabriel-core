from __future__ import annotations

from pydantic import BaseModel

from fastapi import Response, Request, HTTPException

from gabriel.api.errors import AuthenticationError
from gabriel.identity.models import Capability, PrincipalStatus, PrincipalType
from gabriel.identity.principal import Principal
from gabriel.identity.principal_id import PrincipalID

import logging

logger = logging.getLogger(__name__)

class AuthenticatedPrincipal(BaseModel):
    principal: Principal
    token: str


def _capabilities_for_roles(roles: list[str]) -> set[Capability]:
    capabilities: set[Capability] = {
        Capability.AUTHENTICATE,
        Capability.READ_ORGANIZATION,
    }
    role_set = set(roles)

    if "workspace_admin" in role_set:
        capabilities.update(
            {
                Capability.READ_RESOURCE,
                Capability.WRITE_RESOURCE,
                Capability.EXECUTE_WORKFLOW,
                Capability.READ_PRINCIPAL,
                Capability.MANAGE_PRINCIPALS,
                Capability.MANAGE_POLICIES,
            }
        )

    if "member" in role_set:
        capabilities.update(
            {
                Capability.READ_RESOURCE,
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


def _dev_principal_record_for(principal_token: str) -> dict | None:
    return next(
        (entry for entry in DEV_PRINCIPALS if entry["user"]["principal"] == principal_token),
        None,
    )


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
    authorization: str | None = None,
    x_principal_name: str | None = None,
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
    dev_record = _dev_principal_record_for(token)

    display_name = x_principal_name or principal_id.principal_identifier
    capabilities: set[Capability] = set()
    if dev_record is not None:
        display_name = dev_record["user"]["displayName"]
        capabilities = _capabilities_for_roles(dev_record.get("roles", []))

    principal = Principal(
        id=principal_id,
        organization_id=principal_id.org_id,
        principal_type=principal_type,
        display_name=display_name,
        status=PrincipalStatus.ACTIVE,
        capabilities=capabilities,
    )

    return AuthenticatedPrincipal(principal=principal, token=token)

# ── Dev Identity Provider ──────────────────────────────────────────────────

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

class DevLoginRequest(BaseModel):
    userId: str

async def dev_login(body: DevLoginRequest, response: Response):
    match = next((p for p in DEV_PRINCIPALS if p["user"]["id"] == body.userId), None)
    if not match:
        raise HTTPException(status_code=404, detail="Unknown dev principal")

    user = match["user"]
    organization = match["organization"]

    # Build a session view — same shape the frontend Session type expects
    session = {
        "user": {
            "id": user["id"],
            "principal": user["principal"],
            "displayName": user["displayName"],
            "email": user["email"],
            "initials": user["displayName"][0].upper(),
            "avatarUrl": None,
            "roles": match["roles"],
        },
        "organization": {
            "id": organization["id"],
            "name": organization["name"],
            "slug": organization["id"],
        },
        "tenantId": organization["id"],
        "authMethod": "dev",
        "expiresAt": "2099-01-01T00:00:00Z",
        # The principal token — Gateway will use this in Authorization header
        # when calling Core on behalf of the user
        "_principalToken": user["principal"],
    }

    # Set httpOnly cookie so the browser never sees the token
    response.set_cookie(
        key="gabriel_session",
        value=user["principal"],
        httponly=True,
        samesite="lax",
        max_age=8 * 60 * 60,
    )
    return session

async def get_session(request: Request):
    token = request.cookies.get("gabriel_session")
    if not token:
        logger.warning("No gabriel_session cookie found in request")
        raise HTTPException(status_code=401, detail="No session")

    # Find matching principal
    principal_str = token
    match = next(
        (p for p in DEV_PRINCIPALS if p["user"]["principal"] == principal_str), None
    )
    if not match:
        logger.warning("No matching principal found for token: %s", principal_str)
        raise HTTPException(status_code=401, detail="Invalid session")

    user = match["user"]
    organization = match["organization"]

    return {
        "user": {
            "id": user["id"],
            "principal": user["principal"],
            "displayName": user["displayName"],
            "email": user["email"],
            "initials": user["displayName"][0].upper(),
            "avatarUrl": None,
            "roles": match["roles"],
        },
        "organization": {
            "id": organization["id"],
            "name": organization["name"],
            "slug": organization["id"],
        },
        "tenantId": organization["id"],
        "authMethod": "dev",
        "expiresAt": "2099-01-01T00:00:00Z",
    }