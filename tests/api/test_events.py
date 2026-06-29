from __future__ import annotations

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

