"""SessionManager tests (Phase 3)."""
from __future__ import annotations

from gabriel.gateway.sessions import SessionManager


def _create(manager: SessionManager, conversation="grn:acme:conversation/c1:1", **kw):
    defaults = dict(
        org_id="acme",
        principal_id="alice",
        conversation_grn=conversation,
        agent_grn="grn:acme:agent/a1:1",
        provider="ollama",
        model="llama3",
    )
    defaults.update(kw)
    return manager.get_or_create(**defaults)


def test_get_or_create_reuses_session_for_same_chat():
    manager = SessionManager()
    first = _create(manager)
    second = _create(manager)
    assert first.session_id == second.session_id
    assert manager.active_count() == 1


def test_distinct_chats_get_distinct_sessions():
    manager = SessionManager()
    a = _create(manager)
    b = _create(manager, conversation="grn:acme:conversation/c2:1")
    c = _create(manager, principal_id="bob")
    assert len({a.session_id, b.session_id, c.session_id}) == 3
    assert manager.active_count("acme") == 3


def test_record_turn_tracks_usage():
    manager = SessionManager()
    session = _create(manager)
    session.record_turn(tokens=42)
    session.record_turn(tokens=8)
    assert session.turn_count == 2
    assert session.total_tokens == 50
    view = session.public_view()
    assert view["turn_count"] == 2
    assert view["total_tokens"] == 50
    assert view["conversation_grn"] == "grn:acme:conversation/c1:1"


def test_end_session():
    manager = SessionManager()
    session = _create(manager)
    assert manager.end(session.session_id) is True
    assert manager.get(session.session_id) is None
    assert manager.end(session.session_id) is False
    # New chat after ending gets a fresh session.
    fresh = _create(manager)
    assert fresh.session_id != session.session_id


def test_list_active_is_org_scoped():
    manager = SessionManager()
    _create(manager)
    _create(manager, org_id="globex", conversation="grn:globex:conversation/c9:1")
    assert manager.active_count("acme") == 1
    assert manager.active_count("globex") == 1
    assert manager.active_count() == 2
    assert all(s.org_id == "acme" for s in manager.list_active("acme"))


def test_idle_sessions_are_evicted():
    manager = SessionManager(idle_ttl_seconds=60)
    session = _create(manager)
    # Simulate 61 seconds of idleness.
    session.last_activity_at -= 61
    assert manager.get(session.session_id) is None
    assert manager.active_count() == 0


def test_get_or_create_refreshes_routing_info():
    manager = SessionManager()
    _create(manager, model="llama3")
    updated = _create(manager, model="mistral")
    assert updated.model == "mistral"
