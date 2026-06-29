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

