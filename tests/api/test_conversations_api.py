"""API tests for /api/v1/conversations (Phase 2 — Core Business Logic)."""
from __future__ import annotations

from uuid import uuid4


def _unique_org() -> str:
    # The API fallback DB persists across runs — isolate each test in its own org.
    return f"org-{uuid4().hex[:12]}"


def _create(client, headers, title="Support thread", **extra):
    payload = {"title": title, **extra}
    response = client.post("/api/v1/conversations", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_conversations_require_authentication(client):
    assert client.get("/api/v1/conversations").status_code == 401


def test_create_and_get_conversation(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")

    created = _create(client, headers, agent_grn=f"grn:{org}:agent/a1:1")
    assert created["grn"].startswith(f"grn:{org}:conversation/")
    assert created["title"] == "Support thread"
    assert created["status"] == "active"
    assert created["agent_grn"] == f"grn:{org}:agent/a1:1"

    fetched = client.get(f"/api/v1/conversations/{created['grn']}", headers=headers)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["grn"] == created["grn"]


def test_list_conversations_paginated_and_filtered(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    grns = [_create(client, headers, title=f"Thread {i}")["grn"] for i in range(3)]

    # Archive one.
    archived = client.patch(
        f"/api/v1/conversations/{grns[0]}", json={"status": "archived"}, headers=headers
    )
    assert archived.status_code == 200, archived.text

    page = client.get(
        "/api/v1/conversations", params={"limit": 2, "offset": 0}, headers=headers
    ).json()
    assert page["total"] == 3
    assert len(page["items"]) == 2

    active = client.get(
        "/api/v1/conversations", params={"status": "active"}, headers=headers
    ).json()
    assert active["total"] == 2

    archived_list = client.get(
        "/api/v1/conversations", params={"status": "archived"}, headers=headers
    ).json()
    assert archived_list["total"] == 1


def test_conversations_are_tenant_isolated(client, make_auth_headers):
    headers = make_auth_headers(org=_unique_org(), identifier="alice")
    other_headers = make_auth_headers(org=_unique_org(), identifier="bob")

    grn = _create(client, headers)["grn"]
    cross = client.get(f"/api/v1/conversations/{grn}", headers=other_headers)
    assert cross.status_code == 403


def test_message_lifecycle(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    grn = _create(client, headers)["grn"]

    created = client.post(
        f"/api/v1/conversations/{grn}/messages",
        json={
            "role": "assistant",
            "content": "Hello!",
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "model": "gpt-test",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    message = created.json()
    assert message["grn"].startswith(f"grn:{org}:message/")
    assert message["conversation_grn"] == grn
    assert message["total_tokens"] == 15

    client.post(
        f"/api/v1/conversations/{grn}/messages",
        json={"role": "user", "content": "Thanks"},
        headers=headers,
    )

    listing = client.get(f"/api/v1/conversations/{grn}/messages", headers=headers).json()
    assert listing["total"] == 2
    assert [m["content"] for m in listing["items"]] == ["Hello!", "Thanks"]


def test_message_rejected_on_archived_conversation(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    grn = _create(client, headers)["grn"]
    client.patch(
        f"/api/v1/conversations/{grn}", json={"status": "archived"}, headers=headers
    )

    response = client.post(
        f"/api/v1/conversations/{grn}/messages",
        json={"role": "user", "content": "Hi"},
        headers=headers,
    )
    assert response.status_code == 409


def test_delete_conversation_soft(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    grn = _create(client, headers)["grn"]

    deleted = client.delete(f"/api/v1/conversations/{grn}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["state"] == "deleted"

    assert client.get(f"/api/v1/conversations/{grn}", headers=headers).status_code == 404
    assert client.get("/api/v1/conversations", headers=headers).json()["total"] == 0


def test_unknown_role_rejected(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    grn = _create(client, headers)["grn"]

    response = client.post(
        f"/api/v1/conversations/{grn}/messages",
        json={"role": "robot", "content": "Hi"},
        headers=headers,
    )
    assert response.status_code == 422
