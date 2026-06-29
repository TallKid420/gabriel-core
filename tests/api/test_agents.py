from __future__ import annotations


def test_agent_creation_and_execution_emit_events(client, auth_headers):
	create_response = client.post(
		"/agents",
		json={"name": "support-agent", "runtime": "mock", "config": {"temperature": 0.2}},
		headers=auth_headers,
	)
	assert create_response.status_code == 201
	created = create_response.json()
	grn = created["grn"]

	execute_response = client.post(
		f"/agents/{grn}/execute",
		json={"input": {"prompt": "hello"}},
		headers=auth_headers,
	)
	assert execute_response.status_code == 200
	assert execute_response.json()["last_event"] == "agent_executed"

	events_response = client.get("/events", headers=auth_headers)
	assert events_response.status_code == 200
	event_types = [item["type"] for item in events_response.json()["items"]]
	assert "agent_created" in event_types
	assert "agent_executed" in event_types

