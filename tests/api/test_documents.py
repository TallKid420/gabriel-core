"""API tests for document ingestion endpoint."""
from __future__ import annotations

WRITE_HEADERS = {
	"Authorization": "Bearer principal://acme/user/alice",
	"X-Capabilities": "read_resource,write_resource",
	"X-Correlation-ID": "11111111-1111-1111-1111-111111111111",
}

READ_HEADERS = {
	"Authorization": "Bearer principal://acme/user/bob",
	"X-Capabilities": "read_resource",
	"X-Correlation-ID": "22222222-2222-2222-2222-222222222222",
}


def test_upload_document_creates_resource_and_event(client):
	files = {"file": ("notes.md", b"# Heading\n\nBody text", "text/markdown")}
	response = client.post("/documents", headers=WRITE_HEADERS, files=files)
	assert response.status_code == 201, response.text
	body = response.json()
	assert body["resource_type"] == "document"
	assert body["state"] == "active"
	assert body["event_type"] == "resource_created"
	assert body["grn"].startswith("grn:acme:document/")
	assert body["content_pointer"].startswith("disk://acme/documents/")
	assert body["content_hash"] is not None

	# The ResourceCreated event is visible in the event log.
	events = client.get("/events", headers=READ_HEADERS).json()["items"]
	matching = next(
		(
			e for e in events
			if e["type"] == "resource_created" and e["resource_grn"] == body["grn"]
		),
		None,
	)
	assert matching is not None
	assert matching["payload"]["attributes"]["content_pointer"].startswith("disk://acme/documents/")
	assert "normalized_text" not in matching["payload"]["attributes"]


def test_upload_document_denied_without_write_capability(client):
	files = {"file": ("notes.txt", b"hello", "text/plain")}
	response = client.post("/documents", headers=READ_HEADERS, files=files)
	assert response.status_code == 403


def test_uploaded_document_is_retrievable(client):
	files = {"file": ("doc.txt", b"retrievable content", "text/plain")}
	created = client.post("/documents", headers=WRITE_HEADERS, files=files).json()
	got = client.get(f"/documents/{created['grn']}", headers=READ_HEADERS)
	assert got.status_code == 200
	assert got.json()["grn"] == created["grn"]
	assert got.json()["attributes"]["content_pointer"].startswith("disk://acme/documents/")
	assert "normalized_text" not in got.json().get("attributes", {})
