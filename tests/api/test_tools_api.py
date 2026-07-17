"""API tests for /api/v1/tools (V1 — Tool as a Universal Resource)."""
from __future__ import annotations

from uuid import uuid4

import pytest


def _unique_org() -> str:
    # The API fallback DB persists across runs — isolate each test in its own org.
    return f"org-{uuid4().hex[:12]}"


def _create_tool(client, headers, name="calculator", **extra):
    payload = {
        "name": name,
        "description": "Evaluates arithmetic expressions",
        "category": "math",
        **extra,
    }
    response = client.post("/api/v1/tools", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_tools_require_authentication(client):
    assert client.get("/api/v1/tools").status_code == 401


def test_tool_crud_lifecycle(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")

    tool = _create_tool(
        client,
        headers,
        execution_runtime="cloud",
        configuration={"precision": 8},
        labels={"tier": "core"},
    )
    assert tool["grn"].startswith(f"grn:{org}:tool/")
    assert tool["name"] == "calculator"
    assert tool["category"] == "math"
    assert tool["execution_runtime"] == "cloud"
    assert tool["enabled"] is True
    assert tool["configuration"] == {"precision": 8}

    listing = client.get("/api/v1/tools", headers=headers)
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 1
    assert body["items"][0]["grn"] == tool["grn"]

    fetched = client.get(f"/api/v1/tools/{tool['grn']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["description"] == "Evaluates arithmetic expressions"

    patched = client.patch(
        f"/api/v1/tools/{tool['grn']}",
        json={"enabled": False, "description": "Math tool"},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["enabled"] is False
    assert patched.json()["description"] == "Math tool"
    assert patched.json()["version"] == 2

    deleted = client.delete(f"/api/v1/tools/{tool['grn']}", headers=headers)
    assert deleted.status_code == 204
    assert (
        client.get(f"/api/v1/tools/{tool['grn']}", headers=headers).status_code
        == 404
    )


def test_tool_list_filters(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")

    _create_tool(client, headers, name="calc", category="math")
    _create_tool(
        client,
        headers,
        name="mailer",
        category="email",
        enabled=False,
        execution_runtime="enterprise",
    )

    by_category = client.get("/api/v1/tools?category=email", headers=headers)
    assert by_category.status_code == 200
    assert [t["name"] for t in by_category.json()["items"]] == ["mailer"]

    only_enabled = client.get("/api/v1/tools?enabled=true", headers=headers)
    assert [t["name"] for t in only_enabled.json()["items"]] == ["calc"]

    by_runtime = client.get(
        "/api/v1/tools?execution_runtime=enterprise", headers=headers
    )
    assert [t["name"] for t in by_runtime.json()["items"]] == ["mailer"]


def test_tool_invalid_enums_rejected(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")

    bad_category = client.post(
        "/api/v1/tools",
        json={"name": "x", "category": "not-a-category"},
        headers=headers,
    )
    assert bad_category.status_code == 422

    bad_runtime = client.post(
        "/api/v1/tools",
        json={"name": "x", "category": "math", "execution_runtime": "mars"},
        headers=headers,
    )
    assert bad_runtime.status_code == 422


def test_cross_org_tool_access_forbidden(client, make_auth_headers):
    org_a = _unique_org()
    org_b = _unique_org()
    headers_a = make_auth_headers(org=org_a, identifier="alice")
    headers_b = make_auth_headers(org=org_b, identifier="bob")

    tool = _create_tool(client, headers_a)

    assert (
        client.get(f"/api/v1/tools/{tool['grn']}", headers=headers_b).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/v1/tools/{tool['grn']}",
            json={"enabled": False},
            headers=headers_b,
        ).status_code
        == 403
    )
    assert (
        client.delete(f"/api/v1/tools/{tool['grn']}", headers=headers_b).status_code
        == 403
    )
