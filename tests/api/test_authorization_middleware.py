from __future__ import annotations

from gabriel.api.middleware.authorization import _derive_action, _extract_resource_identifier


def test_derive_action_maps_http_method_and_domain(client):
    request = client.build_request("GET", "/memory")
    assert _derive_action(request) == "memory:read"

    request = client.build_request("POST", "/agents/grn:acme:agent/bot:1/execute")
    assert _derive_action(request) == "agent:execute"

    request = client.build_request("PATCH", "/resources/grn:acme:tool/search:1")
    assert _derive_action(request) == "resource:update"


def test_extract_resource_identifier_from_path(client):
    request = client.build_request("GET", "/resources/grn:acme:tool/search:1")
    assert _extract_resource_identifier(request) == "grn:acme:tool/search:1"

    request = client.build_request("POST", "/agents/grn:acme:agent/bot:1/execute")
    assert _extract_resource_identifier(request) == "grn:acme:agent/bot:1"

    request = client.build_request("GET", "/memory")
    assert _extract_resource_identifier(request) == ""


def test_authorization_middleware_allows_and_emits_audit_event(client, make_auth_headers):
    correlation_id = "22222222-2222-2222-2222-222222222222"
    headers = make_auth_headers(correlation_id=correlation_id)

    response = client.get("/memory", headers=headers)

    assert response.status_code == 200
    events = [
        event
        for event in client.app.state.gateway_state.event_store.events_by_type("peel_evaluation")
        if event.correlation_id == correlation_id
    ]
    assert len(events) == 1
    assert events[0].payload["decision"] == "allow"
    assert events[0].payload["action"] == "memory:read"
    assert events[0].payload["path"] == "/memory"


def test_authorization_middleware_denies_and_emits_audit_event(client, make_auth_headers):
    correlation_id = "33333333-3333-3333-3333-333333333333"
    headers = make_auth_headers(
        correlation_id=correlation_id,
        capabilities=("authenticate",),
    )

    response = client.get("/memory", headers=headers)

    assert response.status_code == 403
    events = [
        event
        for event in client.app.state.gateway_state.event_store.events_by_type("peel_evaluation")
        if event.correlation_id == correlation_id
    ]
    assert len(events) == 1
    assert events[0].payload["decision"] == "deny"
    assert events[0].payload["action"] == "memory:read"
    assert events[0].payload["path"] == "/memory"
