from __future__ import annotations


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

