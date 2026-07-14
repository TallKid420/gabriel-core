"""API tests for /api/v1/documents (Phase 4 — Document & Knowledge)."""
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


def _upload(client, headers, filename="notes.txt", text=b"gabriel loves pgvector", **form):
    response = client.post(
        "/api/v1/documents",
        files={"file": (filename, text, "text/plain")},
        data=form,
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_documents_require_authentication(client):
    assert client.get("/api/v1/documents").status_code == 401
    assert client.post("/api/v1/documents").status_code == 401


def test_upload_processes_and_returns_document(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")

    document = _upload(client, headers)
    assert document["grn"].startswith(f"grn:{org}:document/")
    assert document["filename"] == "notes.txt"
    assert document["status"] == "processed"  # process defaults to true
    assert document["chunk_count"] >= 1
    # No Ollama in tests — embedding degrades gracefully.
    assert document["metadata"]["embedded"] is False


def test_upload_without_processing(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    document = _upload(client, headers, process="false")
    assert document["status"] == "uploaded"
    assert document["chunk_count"] == 0


def test_unsupported_type_rejected(client, make_auth_headers):
    headers = make_auth_headers(org=_unique_org(), identifier="alice")
    response = client.post(
        "/api/v1/documents",
        files={"file": ("malware.exe", b"MZ", "application/octet-stream")},
        headers=headers,
    )
    assert response.status_code == 422


def test_list_get_content_and_chunks(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    document = _upload(client, headers, text=b"alpha beta gamma delta")

    listing = client.get("/api/v1/documents", headers=headers)
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 1
    assert body["items"][0]["grn"] == document["grn"]

    fetched = client.get(f"/api/v1/documents/{document['grn']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["grn"] == document["grn"]

    content = client.get(
        f"/api/v1/documents/{document['grn']}/content", headers=headers
    )
    assert content.status_code == 200
    assert "alpha beta" in content.json()["content"]

    chunks = client.get(
        f"/api/v1/documents/{document['grn']}/chunks", headers=headers
    )
    assert chunks.status_code == 200
    chunk_body = chunks.json()
    assert chunk_body["total"] == document["chunk_count"]
    assert chunk_body["items"][0]["chunk_index"] == 0
    assert "alpha" in chunk_body["items"][0]["content"]


def test_reprocess_endpoint(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    document = _upload(client, headers, text=b"one two three four five six")

    response = client.post(
        f"/api/v1/documents/{document['grn']}/process?chunk_size=2&chunk_overlap=0",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["chunk_count"] == 3
    assert body["document"]["chunk_count"] == 3


def test_delete_document(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    document = _upload(client, headers)

    deleted = client.delete(f"/api/v1/documents/{document['grn']}", headers=headers)
    assert deleted.status_code == 204

    assert (
        client.get(f"/api/v1/documents/{document['grn']}", headers=headers).status_code
        == 404
    )
    listing = client.get("/api/v1/documents", headers=headers).json()
    assert listing["total"] == 0


def test_cross_org_access_forbidden(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    document = _upload(client, headers)

    intruder = make_auth_headers(org=_unique_org(), identifier="mallory")
    response = client.get(f"/api/v1/documents/{document['grn']}", headers=intruder)
    assert response.status_code == 403
