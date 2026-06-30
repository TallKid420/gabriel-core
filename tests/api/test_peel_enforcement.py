"""End-to-end tests proving PEEL is enforced on the API gateway.

These tests guard against regressions where PEEL is plumbed but not wired.
They live in Core (Platform Layer) test suite.
"""
from __future__ import annotations


WRITE_HEADERS = {
	"Authorization": "Bearer principal://acme/user/alice",
	"X-Capabilities": "read_resource,write_resource,execute_workflow",
	"X-Correlation-ID": "11111111-1111-1111-1111-111111111111",
}

READ_ONLY_HEADERS = {
	"Authorization": "Bearer principal://acme/user/bob",
	"X-Capabilities": "read_resource",
	"X-Correlation-ID": "22222222-2222-2222-2222-222222222222",
}

NO_CAP_HEADERS = {
	"Authorization": "Bearer principal://acme/user/carol",
	"X-Capabilities": "authenticate",
	"X-Correlation-ID": "33333333-3333-3333-3333-333333333333",
}


def test_write_requires_write_capability(client):
	"""Creating a resource without write_resource is denied by PEEL (403)."""
	response = client.post(
		"/resources",
		headers=READ_ONLY_HEADERS,
		json={"resource_type": "file", "attributes": {"name": "x"}},
	)
	assert response.status_code == 403
	assert "write_resource" in response.json()["detail"]


def test_write_allowed_with_write_capability(client):
	"""A principal holding write_resource may create a resource."""
	response = client.post(
		"/resources",
		headers=WRITE_HEADERS,
		json={"resource_type": "file", "attributes": {"name": "x"}},
	)
	assert response.status_code == 201


def test_read_denied_without_read_capability(client):
	"""GET is blocked by the middleware PEEL pass without read_resource."""
	response = client.get("/memory", headers=NO_CAP_HEADERS)
	assert response.status_code == 403


def test_read_allowed_with_read_capability(client):
	"""GET succeeds with read_resource capability."""
	response = client.get("/memory", headers=READ_ONLY_HEADERS)
	assert response.status_code == 200


def test_cross_tenant_resource_access_denied(client):
	"""A principal from org 'acme' cannot read a resource owned by 'globex'."""
	response = client.get(
		"/resources/grn:globex:file/secret:1",
		headers=WRITE_HEADERS,
	)
	assert response.status_code == 403
	assert "cross-tenant" in response.json()["detail"]


def test_agent_execute_requires_execute_capability(client):
	"""Executing an agent requires execute_workflow capability."""
	response = client.post(
		"/agents/grn:acme:agent/bot:1/execute",
		headers=READ_ONLY_HEADERS,
		json={"input": {}},
	)
	assert response.status_code == 403
