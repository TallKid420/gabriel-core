"""API tests for the DB-backed /api/v1/agents management endpoints (Phase 2)."""
from __future__ import annotations

from uuid import uuid4


def _unique_org() -> str:
    # The API fallback DB persists across runs — isolate each test in its own org.
    return f"org-{uuid4().hex[:12]}"


def _create_payload(name: str) -> dict:
    return {
        "name": name,
        "description": "Answers support tickets",
        "system_prompt": "You are a helpful support agent.",
        "model_config": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.2,
            "max_tokens": 512,
        },
        "allowed_tools": ["search", "kb.lookup"],
        "knowledge_sources": ["grn:acme:document/d1:1"],
        "status": "active",
    }


def test_agent_list_requires_authentication(client):
    response = client.get("/api/v1/agents")
    assert response.status_code == 401


def test_agent_list_empty_for_fresh_org(client, make_auth_headers):
    headers = make_auth_headers(org=_unique_org(), identifier="sam")
    response = client.get("/api/v1/agents", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_agent_create_and_get(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")

    create = client.post(
        "/api/v1/agents", json=_create_payload("support-bot"), headers=headers
    )
    assert create.status_code == 201, create.text
    created = create.json()
    assert created["grn"].startswith(f"grn:{org}:agent/")
    assert created["name"] == "support-bot"
    assert created["status"] == "active"
    assert created["enabled"] is True
    assert created["model_config"]["provider"] == "openai"
    assert created["model_config"]["temperature"] == 0.2
    assert created["allowed_tools"] == ["search", "kb.lookup"]
    assert created["knowledge_sources"] == ["grn:acme:document/d1:1"]

    fetched = client.get(f"/api/v1/agents/{created['grn']}", headers=headers)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["grn"] == created["grn"]


def test_agent_list_scoped_to_tenant(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    other_headers = make_auth_headers(org=_unique_org(), identifier="bob")

    create = client.post(
        "/api/v1/agents", json=_create_payload("tenant-agent"), headers=headers
    )
    assert create.status_code == 201, create.text
    grn = create.json()["grn"]

    mine = client.get("/api/v1/agents", headers=headers).json()
    assert [item["grn"] for item in mine["items"]] == [grn]

    theirs = client.get("/api/v1/agents", headers=other_headers).json()
    assert theirs["items"] == []

    # Direct cross-tenant fetch is forbidden.
    cross = client.get(f"/api/v1/agents/{grn}", headers=other_headers)
    assert cross.status_code == 403


def test_agent_update(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    grn = client.post(
        "/api/v1/agents", json=_create_payload("update-me"), headers=headers
    ).json()["grn"]

    update = client.patch(
        f"/api/v1/agents/{grn}",
        json={
            "description": "Updated",
            "status": "inactive",
            "allowed_tools": ["search"],
            "model_config": {"provider": "anthropic", "model": "claude-3"},
        },
        headers=headers,
    )
    assert update.status_code == 200, update.text
    body = update.json()
    assert body["description"] == "Updated"
    assert body["status"] == "inactive"
    assert body["enabled"] is False
    assert body["allowed_tools"] == ["search"]
    assert body["model_config"]["provider"] == "anthropic"


def test_agent_delete(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    grn = client.post(
        "/api/v1/agents", json=_create_payload("delete-me"), headers=headers
    ).json()["grn"]

    delete = client.delete(f"/api/v1/agents/{grn}", headers=headers)
    assert delete.status_code == 200, delete.text
    assert delete.json()["deleted"] is True

    missing = client.get(f"/api/v1/agents/{grn}", headers=headers)
    assert missing.status_code == 404


def test_agent_unknown_status_rejected(client, make_auth_headers):
    headers = make_auth_headers(org=_unique_org(), identifier="alice")
    payload = _create_payload("bad-status")
    payload["status"] = "nonsense"
    response = client.post("/api/v1/agents", json=payload, headers=headers)
    assert response.status_code == 422
