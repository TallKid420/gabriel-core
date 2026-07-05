"""End-to-end tests proving PEEL is enforced on the API gateway.

These tests guard against regressions where PEEL is plumbed but not wired.
Capabilities are carried in the signed token (not client-supplied headers),
per ADR-008. They live in Core (Platform Layer) test suite.
"""
from __future__ import annotations

import pytest

from tests.api.conftest import issue_token_headers


@pytest.fixture
def write_headers(client):
    return issue_token_headers(
        client,
        identifier="alice",
        capabilities=("authenticate", "read_resource", "write_resource", "execute_workflow"),
    )


@pytest.fixture
def read_only_headers(client):
    return issue_token_headers(
        client,
        identifier="bob",
        capabilities=("authenticate", "read_resource"),
        correlation_id="22222222-2222-2222-2222-222222222222",
    )


@pytest.fixture
def no_cap_headers(client):
    return issue_token_headers(
        client,
        identifier="carol",
        capabilities=("authenticate",),
        correlation_id="33333333-3333-3333-3333-333333333333",
    )


def test_write_requires_write_capability(client, read_only_headers):
	"""Creating a resource without write_resource is denied by PEEL (403)."""
	response = client.post(
		"/resources",
		headers=read_only_headers,
		json={"resource_type": "file", "attributes": {"name": "x"}},
	)
	assert response.status_code == 403
	assert "write_resource" in response.json()["detail"]


def test_write_allowed_with_write_capability(client, write_headers):
	"""A principal holding write_resource may create a resource."""
	response = client.post(
		"/resources",
		headers=write_headers,
		json={"resource_type": "file", "attributes": {"name": "x"}},
	)
	assert response.status_code == 201


def test_read_denied_without_read_capability(client, no_cap_headers):
	"""GET is blocked by the middleware PEEL pass without read_resource."""
	response = client.get("/memory", headers=no_cap_headers)
	assert response.status_code == 403


def test_read_allowed_with_read_capability(client, read_only_headers):
	"""GET succeeds with read_resource capability."""
	response = client.get("/memory", headers=read_only_headers)
	assert response.status_code == 200


def test_cross_tenant_resource_access_denied(client, write_headers):
	"""A principal from org 'acme' cannot read a resource owned by 'globex'."""
	response = client.get(
		"/resources/grn:globex:file/secret:1",
		headers=write_headers,
	)
	assert response.status_code == 403
	assert "cross-tenant" in response.json()["detail"]


def test_agent_execute_requires_execute_capability(client, read_only_headers):
	"""Executing an agent requires execute_workflow capability."""
	response = client.post(
		"/agents/grn:acme:agent/bot:1/execute",
		headers=read_only_headers,
		json={"input": {}},
	)
	assert response.status_code == 403
