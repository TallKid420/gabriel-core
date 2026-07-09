"""HTTP tests for the core-owned agent-specification API.

These prove the endpoints the ``gabriel-desktop`` gateway calls over HTTP are
public (no auth needed for authoring/config), delegate to gabriel-core's
template + store system, and return resolved GRNs.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _specs_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("GABRIEL_AGENT_SPECS_DIR", str(tmp_path / "agent-specs"))
    monkeypatch.setenv("GABRIEL_DEFAULT_ORG_ID", "acme")
    yield


def test_templates_endpoint_is_public_and_lists_legacy_types(client):
    resp = client.get("/api/v1/agent-specs/templates")
    assert resp.status_code == 200
    templates = resp.json()["templates"]
    keys = {t["key"] for t in templates}
    assert {"chat", "engineer", "researcher", "daemon", "server"} <= keys


def test_instantiate_returns_validated_spec_with_resolved_grns(client):
    resp = client.post(
        "/api/v1/agent-specs/instantiate",
        json={"template": "chat", "name": "My Chat"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "My Chat"
    # Wildcard tool bindings are resolved to concrete org-scoped GRNs.
    assert "resolvedTools" in body
    assert all(g.startswith("grn:acme:tool/") for g in body["resolvedTools"])


def test_instantiate_unknown_template_returns_404(client):
    resp = client.post(
        "/api/v1/agent-specs/instantiate", json={"template": "nope"}
    )
    assert resp.status_code == 404


def test_save_list_load_delete_roundtrip(client):
    # Save
    saved = client.post(
        "/api/v1/agent-specs", json={"template": "engineer", "name": "Builder"}
    )
    assert saved.status_code == 201
    assert saved.json()["name"] == "Builder"
    assert "path" in saved.json()

    # List
    listed = client.get("/api/v1/agent-specs")
    assert listed.status_code == 200
    assert "Builder" in listed.json()["specs"]

    # Load
    loaded = client.get("/api/v1/agent-specs/Builder")
    assert loaded.status_code == 200
    assert loaded.json()["name"] == "Builder"

    # Delete
    deleted = client.delete("/api/v1/agent-specs/Builder")
    assert deleted.status_code == 204

    # Gone
    missing = client.get("/api/v1/agent-specs/Builder")
    assert missing.status_code == 404
