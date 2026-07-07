from __future__ import annotations


def test_health_endpoints_are_public(client):
	health = client.get("/health")
	live = client.get("/health/live")
	ready = client.get("/health/ready")

	assert health.status_code == 200
	assert health.json() == {"status": "ok"}
	assert live.status_code == 200
	assert live.json() == {"status": "live"}
	assert ready.status_code == 200
	assert ready.json() == {"status": "ready"}


def test_openapi_paths_are_versioned_except_health(client):
	openapi = client.get("/openapi.json")
	assert openapi.status_code == 200
	paths = openapi.json().get("paths", {})

	assert "/health" in paths
	assert "/api/v1/memory" in paths
	assert "/api/v1/auth/me" in paths
	assert "/memory" not in paths
	assert "/auth/me" not in paths

