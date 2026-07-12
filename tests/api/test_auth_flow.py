"""End-to-end password auth flow: register → login → me → refresh → logout.

Runs against the real app (TestClient) with the fallback SQLite database, so
emails and org names are uuid-suffixed to stay unique across runs.
"""
from __future__ import annotations

import uuid

import pytest


def _signup_payload(**overrides):
    suffix = uuid.uuid4().hex[:10]
    payload = {
        "email": f"owner-{suffix}@example.com",
        "password": "s3cret-password!",
        "display_name": "Owner One",
        "organization_name": f"Test Org {suffix}",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def signup(client):
    payload = _signup_payload()
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return payload, response.json()


def test_register_returns_tokens_and_session(signup):
    payload, data = signup
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["token_type"] == "bearer"
    assert data["session"]["authMethod"] == "password"
    assert data["session"]["user"]["email"] == payload["email"]
    assert data["user"]["email"] == payload["email"]
    assert "password" not in str(data["user"])
    assert data["organization"]["name"] == payload["organization_name"]
    # GRN-addressed user resource in the org's tenancy
    assert data["user"]["grn"].startswith(f"grn:{data['organization']['id']}:user/")


def test_register_duplicate_org_name_conflicts(client, signup):
    payload, _ = signup
    response = client.post(
        "/api/v1/auth/register",
        json=_signup_payload(organization_name=payload["organization_name"]),
    )
    assert response.status_code == 409


def test_login_with_password(client, signup):
    payload, _ = signup
    response = client.post(
        "/api/v1/auth/login",
        json={
            "method": "password",
            "credentials": {"email": payload["email"], "password": payload["password"]},
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["session"]["user"]["roles"] == ["owner"]


def test_login_wrong_password_401(client, signup):
    payload, _ = signup
    response = client.post(
        "/api/v1/auth/login",
        json={
            "method": "password",
            "credentials": {"email": payload["email"], "password": "wrong-password"},
        },
    )
    assert response.status_code == 401
    # Uniform error message (no user enumeration)
    assert "Invalid email or password" in response.text


def test_me_with_access_token(client, signup):
    payload, data = signup
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == payload["display_name"]
    assert body["organization_id"] == data["organization"]["id"]


def test_refresh_rotation_and_reuse_detection(client, signup):
    _, data = signup
    old_refresh = data["refresh_token"]

    response = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert response.status_code == 200, response.text
    rotated = response.json()
    assert rotated["access_token"]
    assert rotated["refresh_token"] != old_refresh

    # Replaying the consumed token fails and revokes the chain.
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert response.status_code == 401
    response = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]}
    )
    assert response.status_code == 401


def test_logout_revokes_refresh_token(client, signup):
    _, data = signup
    response = client.post(
        "/api/v1/auth/logout", json={"refresh_token": data["refresh_token"]}
    )
    assert response.status_code == 200
    response = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]}
    )
    assert response.status_code == 401


def test_users_me_and_org_endpoints(client, signup):
    _, data = signup
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    response = client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["grn"] == data["user"]["grn"]

    org_id = data["organization"]["id"]
    response = client.get(f"/api/v1/organizations/{org_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["org_id"] == org_id

    response = client.get(f"/api/v1/organizations/{org_id}/members", headers=headers)
    assert response.status_code == 200
    members = response.json()["items"]
    assert len(members) == 1
    assert members[0]["role"] == "owner"


def test_cross_org_isolation(client):
    # Two independent organizations
    a_payload, a = _signup_payload(), None
    b_payload = _signup_payload()
    resp_a = client.post("/api/v1/auth/register", json=a_payload)
    resp_b = client.post("/api/v1/auth/register", json=b_payload)
    assert resp_a.status_code == 201 and resp_b.status_code == 201
    a, b = resp_a.json(), resp_b.json()

    headers_a = {"Authorization": f"Bearer {a['access_token']}"}

    # Org A's owner cannot read Org B
    response = client.get(
        f"/api/v1/organizations/{b['organization']['id']}", headers=headers_a
    )
    assert response.status_code == 403

    # Org A's owner cannot read Org B's user by GRN
    response = client.get(f"/api/v1/users/{b['user']['grn']}", headers=headers_a)
    assert response.status_code == 403


def test_invite_teammate_and_member_login(client, signup):
    payload, data = signup
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    org_id = data["organization"]["id"]

    teammate_email = f"member-{uuid.uuid4().hex[:10]}@example.com"
    response = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": teammate_email,
            "password": "another-s3cret!",
            "display_name": "Member Two",
            "role": "member",
        },
    )
    assert response.status_code == 201, response.text

    # The teammate can log in (org disambiguated automatically by email)
    response = client.post(
        "/api/v1/auth/login",
        json={
            "method": "password",
            "credentials": {"email": teammate_email, "password": "another-s3cret!"},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["session"]["organization"]["id"] == org_id

    # Membership list now shows both seats
    response = client.get(f"/api/v1/organizations/{org_id}/members", headers=headers)
    roles = sorted(m["role"] for m in response.json()["items"])
    assert roles == ["member", "owner"]
