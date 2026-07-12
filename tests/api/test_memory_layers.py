"""API tests for /api/v1/memory/layers (Phase 2 — Core Business Logic)."""
from __future__ import annotations

from uuid import uuid4


def _unique_org() -> str:
    # The API fallback DB persists across runs — isolate each test in its own org.
    return f"org-{uuid4().hex[:12]}"


def _create(client, headers, key="prefs.theme", **extra):
    payload = {"key": key, "value": {"mode": "dark"}, "scope": "org", **extra}
    response = client.post("/api/v1/memory/layers", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_memory_layers_require_authentication(client):
    assert client.get("/api/v1/memory/layers").status_code == 401


def test_create_and_get_entry(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")

    created = _create(client, headers, tags=["ui"])
    assert created["grn"].startswith(f"grn:{org}:memory/")
    assert created["key"] == "prefs.theme"
    assert created["value"] == {"mode": "dark"}
    assert created["scope"] == "org"
    assert created["tags"] == ["ui"]

    fetched = client.get(f"/api/v1/memory/layers/{created['grn']}", headers=headers)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["grn"] == created["grn"]


def test_duplicate_key_conflict(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    _create(client, headers)

    duplicate = client.post(
        "/api/v1/memory/layers",
        json={"key": "prefs.theme", "value": 1, "scope": "org"},
        headers=headers,
    )
    assert duplicate.status_code == 409


def test_list_entries_with_filters(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    _create(client, headers, key="a", tags=["ui"])
    _create(client, headers, key="b", tags=["backend"])
    _create(
        client,
        headers,
        key="c",
        scope="agent",
        subject_grn=f"grn:{org}:agent/a1:1",
    )

    everything = client.get("/api/v1/memory/layers", headers=headers).json()
    assert everything["total"] == 3

    org_scope = client.get(
        "/api/v1/memory/layers", params={"scope": "org"}, headers=headers
    ).json()
    assert org_scope["total"] == 2

    tagged = client.get(
        "/api/v1/memory/layers", params={"tag": "ui"}, headers=headers
    ).json()
    assert [item["key"] for item in tagged["items"]] == ["a"]


def test_update_entry(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    grn = _create(client, headers)["grn"]

    updated = client.patch(
        f"/api/v1/memory/layers/{grn}",
        json={"value": {"mode": "light"}, "tags": ["ui", "prefs"]},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["value"] == {"mode": "light"}
    assert body["tags"] == ["ui", "prefs"]


def test_delete_entry(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    grn = _create(client, headers)["grn"]

    deleted = client.delete(f"/api/v1/memory/layers/{grn}", headers=headers)
    assert deleted.status_code == 204, deleted.text

    assert client.get(f"/api/v1/memory/layers/{grn}", headers=headers).status_code == 404


def test_entries_are_tenant_isolated(client, make_auth_headers):
    headers = make_auth_headers(org=_unique_org(), identifier="alice")
    other_headers = make_auth_headers(org=_unique_org(), identifier="bob")
    grn = _create(client, headers)["grn"]

    cross = client.get(f"/api/v1/memory/layers/{grn}", headers=other_headers)
    assert cross.status_code == 403


def test_invalid_scope_rejected(client, make_auth_headers):
    headers = make_auth_headers(org=_unique_org(), identifier="alice")
    response = client.post(
        "/api/v1/memory/layers",
        json={"key": "k", "value": 1, "scope": "galaxy"},
        headers=headers,
    )
    assert response.status_code == 422
