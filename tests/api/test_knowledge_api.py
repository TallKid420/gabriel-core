"""API tests for /api/v1/knowledge (Phase 4 — knowledge sources & search)."""
from __future__ import annotations

from uuid import uuid4

import pytest


def _unique_org() -> str:
    # The API fallback DB persists across runs — isolate each test in its own org.
    return f"org-{uuid4().hex[:12]}"


@pytest.fixture(autouse=True)
def _tmp_content_root(tmp_path, monkeypatch):
    """Keep uploaded file content out of the repo's tracked .gabriel dir."""
    monkeypatch.setenv("GABRIEL_CONTENT_ROOT", str(tmp_path / "content"))


def _create_source(client, headers, name="Handbook", **extra):
    response = client.post(
        "/api/v1/knowledge/sources",
        json={"name": name, **extra},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _upload_document(client, headers, filename="notes.txt", text=b"gabriel retrieval augmented generation"):
    response = client.post(
        "/api/v1/documents",
        files={"file": (filename, text, "text/plain")},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_knowledge_requires_authentication(client):
    assert client.get("/api/v1/knowledge/sources").status_code == 401
    assert client.post("/api/v1/knowledge/sources", json={"name": "x"}).status_code == 401
    assert client.post("/api/v1/knowledge/search", json={"query": "x"}).status_code == 401


def test_source_crud_lifecycle(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")

    source = _create_source(client, headers, description="Company handbook")
    assert source["grn"].startswith(f"grn:{org}:knowledge_source/")
    assert source["name"] == "Handbook"
    assert source["status"] == "active"
    assert source["document_count"] == 0

    listing = client.get("/api/v1/knowledge/sources", headers=headers)
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 1
    assert body["items"][0]["grn"] == source["grn"]

    fetched = client.get(f"/api/v1/knowledge/sources/{source['grn']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["description"] == "Company handbook"

    patched = client.patch(
        f"/api/v1/knowledge/sources/{source['grn']}",
        json={"name": "HR Handbook", "status": "archived"},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "HR Handbook"
    assert patched.json()["status"] == "archived"

    deleted = client.delete(
        f"/api/v1/knowledge/sources/{source['grn']}", headers=headers
    )
    assert deleted.status_code == 204
    assert (
        client.get(
            f"/api/v1/knowledge/sources/{source['grn']}", headers=headers
        ).status_code
        == 404
    )


def test_attach_and_detach_document(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")

    source = _create_source(client, headers)
    document = _upload_document(client, headers)

    attached = client.post(
        f"/api/v1/knowledge/sources/{source['grn']}/documents",
        json={"document_grn": document["grn"]},
        headers=headers,
    )
    assert attached.status_code == 201, attached.text

    refreshed = client.get(
        f"/api/v1/knowledge/sources/{source['grn']}", headers=headers
    ).json()
    assert refreshed["document_count"] == 1

    members = client.get(
        f"/api/v1/knowledge/sources/{source['grn']}/documents", headers=headers
    )
    assert members.status_code == 200
    members_body = members.json()
    assert members_body["total"] == 1
    assert members_body["items"][0]["grn"] == document["grn"]
    assert members_body["items"][0]["knowledge_source_grn"] == source["grn"]

    detached = client.post(
        f"/api/v1/knowledge/sources/{source['grn']}/documents/detach",
        json={"document_grn": document["grn"]},
        headers=headers,
    )
    assert detached.status_code == 200, detached.text

    refreshed = client.get(
        f"/api/v1/knowledge/sources/{source['grn']}", headers=headers
    ).json()
    assert refreshed["document_count"] == 0


def test_search_returns_uploaded_content(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")

    _upload_document(
        client,
        headers,
        filename="handbook.txt",
        text=b"the vacation policy grants twenty days per year",
    )

    # No Ollama in tests — the retriever degrades to keyword search.
    response = client.post(
        "/api/v1/knowledge/search",
        json={"query": "vacation policy"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] >= 1
    assert any("vacation policy" in item["content"] for item in body["items"])


def test_search_scoped_to_org(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    _upload_document(client, headers, text=b"secret roadmap for project gabriel")

    intruder = make_auth_headers(org=_unique_org(), identifier="mallory")
    response = client.post(
        "/api/v1/knowledge/search",
        json={"query": "secret roadmap"},
        headers=intruder,
    )
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_cross_org_source_access_forbidden(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    source = _create_source(client, headers)

    intruder = make_auth_headers(org=_unique_org(), identifier="mallory")
    response = client.get(
        f"/api/v1/knowledge/sources/{source['grn']}", headers=intruder
    )
    assert response.status_code == 403
