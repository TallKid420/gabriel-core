"""API tests for /api/v1/gateway (Phase 3 — Gateway AI Runtime)."""
from __future__ import annotations

import json
from uuid import uuid4

from gabriel.gateway.providers.registry import ProviderRegistry

from tests.gateway.conftest import FakeProvider


def _unique_org() -> str:
    # The API fallback DB persists across runs — isolate each test in its own org.
    return f"org-{uuid4().hex[:12]}"


def _install_fake_provider(client, script=None) -> FakeProvider:
    """Swap the app's provider registry for one backed by a FakeProvider."""
    provider = FakeProvider(script=script)
    registry = ProviderRegistry(default_provider="fake")
    registry.register(provider)
    client.app.state.llm_provider_registry = registry
    return provider


def _create_agent(client, headers, *, org: str, status: str = "active") -> str:
    response = client.post(
        "/api/v1/agents",
        json={
            "name": f"gw-agent-{uuid4().hex[:6]}",
            "system_prompt": "You are a concise assistant.",
            "model_config": {"model": "fake-model", "provider": "fake"},
            "status": status,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["grn"]


def _create_conversation(client, headers, *, agent_grn: str | None = None) -> str:
    payload: dict = {"title": "Gateway thread"}
    if agent_grn:
        payload["agent_grn"] = agent_grn
    response = client.post("/api/v1/conversations", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["grn"]


def _parse_sse(raw: str) -> list[tuple[str, dict]]:
    frames = []
    for block in raw.strip().split("\n\n"):
        event, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if event is not None:
            frames.append((event, data))
    return frames


def test_gateway_requires_authentication(client):
    assert client.get("/api/v1/gateway/providers").status_code == 401
    assert client.post(
        "/api/v1/gateway/chat", json={"conversation_grn": "grn:x:conversation/c:1", "content": "hi"}
    ).status_code == 401


def test_list_providers_reports_health(client, make_auth_headers):
    _install_fake_provider(client)
    headers = make_auth_headers(org=_unique_org())

    response = client.get("/api/v1/gateway/providers", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["default_provider"] == "fake"
    assert body["items"] == [
        {"name": "fake", "default": True, "healthy": True, "detail": "fake ok"}
    ]


def test_list_provider_models(client, make_auth_headers):
    _install_fake_provider(client)
    headers = make_auth_headers(org=_unique_org())

    response = client.get("/api/v1/gateway/providers/fake/models", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["items"] == [
        {"name": "fake-model", "provider": "fake", "metadata": {}}
    ]

    missing = client.get("/api/v1/gateway/providers/nope/models", headers=headers)
    assert missing.status_code == 404


def test_list_runtime_tools(client, make_auth_headers):
    headers = make_auth_headers(org=_unique_org())
    response = client.get("/api/v1/gateway/tools", headers=headers)
    assert response.status_code == 200, response.text
    names = [spec["function"]["name"] for spec in response.json()["items"]]
    assert "current_datetime" in names


def test_stream_chat_turn_end_to_end(client, make_auth_headers):
    _install_fake_provider(client, script=[{"text": "Hello there"}])
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    agent_grn = _create_agent(client, headers, org=org)
    conversation_grn = _create_conversation(client, headers, agent_grn=agent_grn)

    with client.stream(
        "POST",
        "/api/v1/gateway/chat/stream",
        json={"conversation_grn": conversation_grn, "content": "Hi!"},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        raw = "".join(response.iter_text())

    frames = _parse_sse(raw)
    events = [event for event, _ in frames]
    assert events[0] == "session"
    assert "message" in events
    assert "token" in events
    assert events[-1] == "done"

    streamed = "".join(data["delta"] for event, data in frames if event == "token")
    assert streamed == "Hello there"

    done = dict(frames)["done"]
    assert done["model"] == "fake-model"
    assert done["usage"]["total_tokens"] == 12

    # Both the user and assistant messages were persisted on the conversation.
    messages = client.get(
        f"/api/v1/conversations/{conversation_grn}/messages", headers=headers
    ).json()
    roles = [m["role"] for m in messages["items"]]
    assert roles == ["user", "assistant"]
    assert messages["items"][1]["content"] == "Hello there"


def test_buffered_chat_turn(client, make_auth_headers):
    _install_fake_provider(client, script=[{"text": "Buffered reply"}])
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    agent_grn = _create_agent(client, headers, org=org)
    conversation_grn = _create_conversation(client, headers, agent_grn=agent_grn)

    response = client.post(
        "/api/v1/gateway/chat",
        json={"conversation_grn": conversation_grn, "content": "Hi!"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["content"] == "Buffered reply"
    assert body["model"] == "fake-model"


def test_chat_without_model_is_rejected(client, make_auth_headers):
    _install_fake_provider(client)
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    # Conversation without an agent and no model override → 422.
    conversation_grn = _create_conversation(client, headers)

    response = client.post(
        "/api/v1/gateway/chat",
        json={"conversation_grn": conversation_grn, "content": "Hi!"},
        headers=headers,
    )
    assert response.status_code == 422
    assert "No model configured" in response.json()["detail"]


def test_chat_is_tenant_isolated(client, make_auth_headers):
    _install_fake_provider(client)
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    other_headers = make_auth_headers(org=_unique_org(), identifier="bob")
    agent_grn = _create_agent(client, headers, org=org)
    conversation_grn = _create_conversation(client, headers, agent_grn=agent_grn)

    cross = client.post(
        "/api/v1/gateway/chat",
        json={"conversation_grn": conversation_grn, "content": "Hi!"},
        headers=other_headers,
    )
    assert cross.status_code == 403


def test_sessions_lifecycle(client, make_auth_headers):
    _install_fake_provider(client, script=[{"text": "Reply"}])
    org = _unique_org()
    headers = make_auth_headers(org=org, identifier="alice")
    agent_grn = _create_agent(client, headers, org=org)
    conversation_grn = _create_conversation(client, headers, agent_grn=agent_grn)

    chat = client.post(
        "/api/v1/gateway/chat",
        json={"conversation_grn": conversation_grn, "content": "Hi!"},
        headers=headers,
    )
    assert chat.status_code == 200, chat.text

    sessions = client.get("/api/v1/gateway/sessions", headers=headers).json()
    ours = [s for s in sessions["items"] if s["conversation_grn"] == conversation_grn]
    assert len(ours) == 1
    session_id = ours[0]["session_id"]

    # Other orgs cannot see or end the session.
    other_headers = make_auth_headers(org=_unique_org(), identifier="bob")
    other = client.get("/api/v1/gateway/sessions", headers=other_headers).json()
    assert all(s["conversation_grn"] != conversation_grn for s in other["items"])
    assert (
        client.delete(f"/api/v1/gateway/sessions/{session_id}", headers=other_headers).status_code
        == 404
    )

    ended = client.delete(f"/api/v1/gateway/sessions/{session_id}", headers=headers)
    assert ended.status_code == 200
    assert ended.json() == {"session_id": session_id, "ended": True}

    remaining = client.get("/api/v1/gateway/sessions", headers=headers).json()
    assert all(s["session_id"] != session_id for s in remaining["items"])
