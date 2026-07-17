from __future__ import annotations

import os

from fastapi.testclient import TestClient

from gabriel.api.app import create_app
from gabriel.api.dependencies import get_event_streamer


class _OneShotEventStreamer:
	async def stream_events(self, organization_id: str):
		yield ": connected\n\n"


def test_event_lookup_and_stream_placeholder(client, auth_headers):
	create = client.post(
		"/resources",
		json={"resource_type": "workflow", "attributes": {"name": "onboarding"}},
		headers=auth_headers,
	)
	assert create.status_code == 201

	events = client.get("/events", headers=auth_headers)
	assert events.status_code == 200
	items = events.json()["items"]
	assert len(items) >= 1

	first_event_id = items[0]["id"]
	detail = client.get(f"/events/{first_event_id}", headers=auth_headers)
	assert detail.status_code == 200
	assert detail.json()["id"] == first_event_id

	client.app.dependency_overrides[get_event_streamer] = lambda: _OneShotEventStreamer()
	try:
		with client.stream("GET", "/events/stream", headers=auth_headers) as stream:
			assert stream.status_code == 200
			assert "text/event-stream" in stream.headers["content-type"]
	finally:
		client.app.dependency_overrides.pop(get_event_streamer, None)


def test_resource_created_survives_app_restart(auth_headers):
	app_a = create_app()
	with TestClient(app_a) as client_a:
		create_response = client_a.post(
			"/resources",
			json={
				"resource_type": "workflow",
				"resource_id": "restart-proof-resource",
				"attributes": {"name": "survive-restart"},
			},
			headers=auth_headers,
		)
		assert create_response.status_code == 201
		grn = create_response.json()["grn"]

	app_b = create_app()
	with TestClient(app_b) as client_b:
		get_response = client_b.get(f"/resources/{grn}", headers=auth_headers)
		assert get_response.status_code == 200
		body = get_response.json()
		assert body["grn"] == grn
		assert body["attributes"] == {"name": "survive-restart"}


def test_create_app_uses_env_loaded_before_startup(monkeypatch):
	monkeypatch.setenv("GABRIEL_OLLAMA_BASE_URL", "http://dotenv-test:11434")

	app = create_app()
	with TestClient(app):
		provider = app.state.llm_provider_registry.get("ollama")

	assert provider.base_url == os.environ["GABRIEL_OLLAMA_BASE_URL"]

