from __future__ import annotations


def test_dev_principals_is_public(client):
	response = client.get("/auth/dev/principals")
	assert response.status_code == 200
	assert isinstance(response.json(), list)


def test_session_without_cookie_is_unauthorized(client):
	response = client.get("/auth/session")
	assert response.status_code == 401


def test_protected_endpoints_require_bearer_token(client):
	response = client.get("/memory")
	assert response.status_code == 401


def test_invalid_bearer_token_is_rejected(client):
	response = client.get("/memory", headers={"Authorization": "Bearer not-a-principal-token"})
	assert response.status_code == 401


def test_valid_bearer_token_allows_access(client, auth_headers):
	response = client.get("/memory", headers=auth_headers)
	assert response.status_code == 200
	assert response.json() == {"items": []}


def test_dev_login_is_public_and_sets_session_cookie(client):
	response = client.post("/auth/dev/login", json={"userId": "user_insurance_alice"})
	assert response.status_code == 200
	assert response.json()["user"]["id"] == "user_insurance_alice"
	assert "gabriel_session=" in response.headers.get("set-cookie", "")


def test_session_endpoint_uses_cookie_from_dev_login(client):
	login_response = client.post("/auth/dev/login", json={"userId": "user_insurance_alice"})
	assert login_response.status_code == 200

	session_response = client.get("/auth/session")
	assert session_response.status_code == 200
	assert session_response.json()["tenantId"] == "org_insurance"


def test_session_without_cookie_is_unauthorized(client):
	response = client.get("/auth/session")
	assert response.status_code == 401


def test_logout_is_public(client):
	response = client.post("/auth/logout")
	assert response.status_code == 200
	assert response.json() == {"ok": True}

