"""Integration tests for the authentication endpoints and session middleware."""
from __future__ import annotations


def test_jwks_is_public_and_exposes_keys(client):
	response = client.get("/api/v1/auth/jwks")
	assert response.status_code == 200
	body = response.json()
	assert "keys" in body and len(body["keys"]) >= 1
	key = body["keys"][0]
	assert key["kty"] == "RSA"
	assert key["alg"] == "RS256"
	assert key["kid"]


def test_login_issues_signed_token_and_cookie(client):
	response = client.post("/api/v1/auth/login", json={"method": "dev", "userId": "u_alice"})
	assert response.status_code == 200
	body = response.json()
	assert body["token_type"] == "bearer"
	assert body["access_token"]
	assert body["session"]["tenantId"] == "org_harbor"
	assert "gabriel_session=" in response.headers.get("set-cookie", "")


def test_login_unknown_user_is_unauthorized(client):
	response = client.post("/api/v1/auth/login", json={"userId": "u_nobody"})
	assert response.status_code == 401


def test_login_unknown_method_is_bad_request(client):
	response = client.post("/api/v1/auth/login", json={"method": "saml", "userId": "u_alice"})
	assert response.status_code == 400


def test_me_requires_authentication(client):
	assert client.get("/api/v1/auth/me").status_code == 401


def test_me_returns_principal_for_bearer_token(client):
	login = client.post("/api/v1/auth/login", json={"userId": "u_alice"})
	token = login.json()["access_token"]

	response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
	assert response.status_code == 200
	body = response.json()
	assert body["principal_id"] == "principal://org_harbor/user/alice"
	assert body["organization_id"] == "org_harbor"
	assert "write_resource" in body["capabilities"]


def test_protected_endpoint_requires_token(client):
	assert client.get("/api/v1/memory").status_code == 401


def test_forged_principal_token_is_rejected(client):
	"""A raw principal:// string is no longer a valid credential (bypass closed)."""
	response = client.get(
		"/api/v1/memory",
		headers={"Authorization": "Bearer principal://acme/user/alice"},
	)
	assert response.status_code == 401


def test_valid_token_allows_access(client, auth_headers):
	response = client.get("/api/v1/memory", headers=auth_headers)
	assert response.status_code == 200
	assert response.json() == {"items": []}


def test_login_then_cookie_authenticates_protected_endpoint(client):
	client.post("/api/v1/auth/login", json={"userId": "u_alice"})
	# Cookie is now stored by the test client and used for subsequent requests.
	response = client.get("/api/v1/memory")
	assert response.status_code == 200


def test_logout_clears_session(client):
	client.post("/api/v1/auth/login", json={"userId": "u_alice"})
	assert client.get("/api/v1/auth/me").status_code == 200

	logout = client.post("/api/v1/auth/logout")
	assert logout.status_code == 200
	assert logout.json() == {"ok": True}

	# Cookie cleared -> no longer authenticated.
	assert client.get("/api/v1/auth/me").status_code == 401


# ── Backwards-compatible development endpoints ──────────────────────────────


def test_dev_principals_is_public(client):
	response = client.get("/api/v1/auth/dev/principals")
	assert response.status_code == 200
	assert isinstance(response.json(), list)
	assert len(response.json()) >= 1


def test_dev_login_sets_session_cookie(client):
	response = client.post("/api/v1/auth/dev/login", json={"userId": "u_alice"})
	assert response.status_code == 200
	assert response.json()["user"]["id"] == "u_alice"
	assert "gabriel_session=" in response.headers.get("set-cookie", "")


def test_session_endpoint_uses_cookie_from_dev_login(client):
	assert client.post("/api/v1/auth/dev/login", json={"userId": "u_alice"}).status_code == 200
	session_response = client.get("/api/v1/auth/session")
	assert session_response.status_code == 200
	assert session_response.json()["tenantId"] == "org_harbor"


def test_session_without_cookie_is_unauthorized(client):
	assert client.get("/api/v1/auth/session").status_code == 401
