"""API tests for the DB-backed /api/v1/notifications endpoints (Phase 2).

Notifications are created from domain events by :class:`NotificationService`
(there is deliberately no public creation endpoint), so these tests seed the
API's database directly through the app's session factory.
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

from gabriel.notification.service import NotificationService


def _unique_org() -> str:
    # The API fallback DB persists across runs — isolate each test in its own org.
    return f"org-{uuid4().hex[:12]}"


def _recipient_for(org: str, identifier: str) -> str:
    """Mirror the router's fallback recipient (principal id, no user record)."""
    from gabriel.identity import PrincipalID

    return str(
        PrincipalID(org_id=org, principal_type="user", principal_identifier=identifier)
    )


def _seed_notification(client, org: str, recipient: str, title: str) -> str:
    """Insert a notification through the service against the app's database."""
    session_factory = client.app.state.db_session_factory

    async def _seed() -> str:
        async with session_factory() as session:
            notification = await NotificationService(session).create_notification(
                org,
                recipient,
                type="resource_created",
                title=title,
                body="details",
            )
            return str(notification.grn)

    return asyncio.run(_seed())


def test_notifications_require_authentication(client):
    assert client.get("/api/v1/notifications").status_code == 401


def test_list_notifications_empty(client, make_auth_headers):
    headers = make_auth_headers(org=_unique_org(), identifier="alice")
    response = client.get("/api/v1/notifications", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["unread_count"] == 0


def test_list_and_mark_read(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    recipient = _recipient_for(org, "alice")
    grn = _seed_notification(client, org, recipient, "You have a new agent")
    _seed_notification(client, org, recipient, "Second alert")

    listing = client.get("/api/v1/notifications", headers=headers).json()
    assert listing["total"] == 2
    assert listing["unread_count"] == 2
    assert {item["title"] for item in listing["items"]} == {
        "You have a new agent",
        "Second alert",
    }

    marked = client.post(f"/api/v1/notifications/{grn}/read", headers=headers)
    assert marked.status_code == 200, marked.text
    assert marked.json()["read"] is True
    assert marked.json()["read_at"] is not None

    unread = client.get(
        "/api/v1/notifications", params={"unread_only": "true"}, headers=headers
    ).json()
    assert unread["total"] == 1
    assert unread["items"][0]["title"] == "Second alert"


def test_mark_all_read(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    recipient = _recipient_for(org, "alice")
    for i in range(3):
        _seed_notification(client, org, recipient, f"Alert {i}")

    response = client.post("/api/v1/notifications/read-all", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True, "marked_read": 3}

    listing = client.get("/api/v1/notifications", headers=headers).json()
    assert listing["unread_count"] == 0


def test_notifications_are_recipient_scoped(client, make_auth_headers):
    org = _unique_org()
    alice_headers = make_auth_headers(org=org, identifier="alice")
    bob_headers = make_auth_headers(org=org, identifier="bob")
    grn = _seed_notification(client, org, _recipient_for(org, "alice"), "For Alice")

    assert client.get("/api/v1/notifications", headers=bob_headers).json()["total"] == 0
    # Bob cannot mark Alice's notification read.
    assert (
        client.post(f"/api/v1/notifications/{grn}/read", headers=bob_headers).status_code
        == 404
    )


def test_legacy_patch_alias_marks_read(client, make_auth_headers):
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    grn = _seed_notification(client, org, _recipient_for(org, "alice"), "Legacy patch")

    response = client.patch(f"/api/v1/notifications/{grn}", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["read"] is True
