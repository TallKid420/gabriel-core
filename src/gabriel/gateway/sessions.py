"""Ephemeral chat session tracking (Phase 3 — Gateway AI Runtime).

A :class:`ChatSession` records that *a principal* is chatting in *a
conversation* with *an agent* through *a provider/model*. Sessions live only
in process memory — they are deliberately **not** persisted (the durable
record of a chat is the conversation + messages owned by the Phase-2 slices).

Sessions expire after ``idle_ttl_seconds`` without activity; expired entries
are lazily evicted on access.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

DEFAULT_IDLE_TTL_SECONDS = 30 * 60  # 30 minutes


@dataclass
class ChatSession:
    """One active chat: principal ↔ conversation ↔ agent."""

    session_id: str
    org_id: str
    principal_id: str
    conversation_grn: str
    agent_grn: str | None = None
    provider: str = ""
    model: str = ""
    created_at: float = field(default_factory=time.monotonic)
    last_activity_at: float = field(default_factory=time.monotonic)
    turn_count: int = 0
    total_tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        self.last_activity_at = time.monotonic()

    def record_turn(self, tokens: int = 0) -> None:
        self.turn_count += 1
        self.total_tokens += tokens
        self.touch()

    def idle_seconds(self) -> float:
        return time.monotonic() - self.last_activity_at

    def public_view(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "org_id": self.org_id,
            "principal_id": self.principal_id,
            "conversation_grn": self.conversation_grn,
            "agent_grn": self.agent_grn,
            "provider": self.provider,
            "model": self.model,
            "turn_count": self.turn_count,
            "total_tokens": self.total_tokens,
            "idle_seconds": round(self.idle_seconds(), 3),
        }


class SessionManager:
    """In-memory manager of active chat sessions (org-scoped views).

    Keyed by ``(org_id, principal_id, conversation_grn)`` so a user resuming
    the same conversation reuses one session instead of leaking new ones.
    """

    def __init__(self, idle_ttl_seconds: float = DEFAULT_IDLE_TTL_SECONDS) -> None:
        self._idle_ttl = idle_ttl_seconds
        self._by_id: dict[str, ChatSession] = {}
        self._by_key: dict[tuple[str, str, str], str] = {}

    # ------------------------------------------------------------------

    def _evict_expired(self) -> None:
        expired = [
            sid
            for sid, session in self._by_id.items()
            if session.idle_seconds() > self._idle_ttl
        ]
        for sid in expired:
            self._remove(sid)

    def _remove(self, session_id: str) -> ChatSession | None:
        session = self._by_id.pop(session_id, None)
        if session is not None:
            self._by_key.pop(
                (session.org_id, session.principal_id, session.conversation_grn),
                None,
            )
        return session

    # ------------------------------------------------------------------

    def get_or_create(
        self,
        *,
        org_id: str,
        principal_id: str,
        conversation_grn: str,
        agent_grn: str | None = None,
        provider: str = "",
        model: str = "",
    ) -> ChatSession:
        """Return the live session for this chat, creating one if needed."""
        self._evict_expired()
        key = (org_id, principal_id, conversation_grn)
        session_id = self._by_key.get(key)
        if session_id is not None and session_id in self._by_id:
            session = self._by_id[session_id]
            # Keep routing info fresh (agent/model may change mid-conversation).
            if agent_grn:
                session.agent_grn = agent_grn
            if provider:
                session.provider = provider
            if model:
                session.model = model
            session.touch()
            return session

        session = ChatSession(
            session_id=str(uuid4()),
            org_id=org_id,
            principal_id=principal_id,
            conversation_grn=conversation_grn,
            agent_grn=agent_grn,
            provider=provider,
            model=model,
        )
        self._by_id[session.session_id] = session
        self._by_key[key] = session.session_id
        return session

    def get(self, session_id: str) -> ChatSession | None:
        self._evict_expired()
        return self._by_id.get(session_id)

    def end(self, session_id: str) -> bool:
        """Terminate a session; returns True when one was removed."""
        return self._remove(session_id) is not None

    def list_active(self, org_id: str | None = None) -> list[ChatSession]:
        self._evict_expired()
        sessions = list(self._by_id.values())
        if org_id is not None:
            sessions = [s for s in sessions if s.org_id == org_id]
        return sorted(sessions, key=lambda s: s.last_activity_at, reverse=True)

    def active_count(self, org_id: str | None = None) -> int:
        return len(self.list_active(org_id))
