from __future__ import annotations


def test_agent_list_requires_authentication(client):
        response = client.get("/agents")
        assert response.status_code == 401


def test_agent_list_returns_empty_list_for_authenticated_user_with_no_agents(client, make_auth_headers):
        other_headers = make_auth_headers(
                org="initech",
                identifier="sam",
                capabilities=("read_resource", "write_resource", "execute_workflow"),
                correlation_id="55555555-5555-5555-5555-555555555555",
        )

        response = client.get("/agents", headers=other_headers)
        assert response.status_code == 200
        assert response.json() == []


def test_agent_list_is_scoped_to_authenticated_tenant(client, auth_headers):
        create_response = client.post(
                "/agents",
                json={
                        "name": "support-agent",
                        "runtime": "mock",
                        "config": {"provider": "openai", "model": "gpt-4o-mini"},
                },
                headers=auth_headers,
        )
        assert create_response.status_code == 201
        created_grn = create_response.json()["grn"]

        response = client.get("/agents", headers=auth_headers)
        assert response.status_code == 200
        agents = response.json()
        match = next(item for item in agents if item["id"] == created_grn)
        assert match["name"] == "support-agent"
        assert match["status"] == "active"
        assert match["enabled"] is True
        assert match["provider"] == "openai"
        assert match["model"] == "gpt-4o-mini"


def test_agent_list_does_not_cross_tenants(client, auth_headers, make_auth_headers):
        create_response = client.post(
                "/agents",
                json={"name": "tenant-agent", "runtime": "mock", "config": {}},
                headers=auth_headers,
        )
        assert create_response.status_code == 201
        created_grn = create_response.json()["grn"]

        other_headers = make_auth_headers(
                org="globex",
                identifier="bob",
                capabilities=("read_resource", "write_resource", "execute_workflow"),
                correlation_id="44444444-4444-4444-4444-444444444444",
        )

        response = client.get("/agents", headers=other_headers)
        assert response.status_code == 200
        assert all(item["id"] != created_grn for item in response.json())
        assert response.json() == []


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


def test_deleted_agent_is_removed_from_agent_list(client, auth_headers):
        create_response = client.post(
                "/agents",
                json={"name": "delete-me", "runtime": "mock", "config": {}},
                headers=auth_headers,
        )
        assert create_response.status_code == 201
        grn = create_response.json()["grn"]

        delete_response = client.delete(f"/agents/{grn}", headers=auth_headers)
        assert delete_response.status_code == 200
        assert delete_response.json() == {"deleted": True, "grn": grn}

        list_response = client.get("/agents", headers=auth_headers)
        assert list_response.status_code == 200
        assert all(item["id"] != grn for item in list_response.json())

        events_response = client.get("/events", headers=auth_headers)
        assert events_response.status_code == 200
        event_types = [item["type"] for item in events_response.json()["items"]]
        assert "agent_deleted" in event_types

