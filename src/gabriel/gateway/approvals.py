"""Human-in-the-loop tool approval bridge (Phase 3 — Gateway AI Runtime).

Some tools carry :class:`~gabriel.tool.models.SafetyLevel.REQUIRES_CONFIRMATION`.
When the LLM requests such a tool mid-turn, the streaming chat loop must:

1. emit a ``tool_approval_required`` SSE event to the client and **pause**;
2. wait for the user's accept/deny decision, which arrives on a *separate*
   HTTP request (``POST /gateway/chat/approval``);
3. resume — executing the tool on accept, or injecting a denial message on
   deny.

Because SSE is one-directional, the paused stream and the inbound decision
live in two different requests. :class:`ApprovalRegistry` is the in-process
rendezvous that connects them: the stream registers a pending approval keyed
by ``(session_id, tool_name)`` and awaits an :class:`asyncio.Event`; the
approval endpoint resolves that key, waking the stream.

The registry is a single app-wide instance (see
``gabriel.api.dependencies``) so both requests share the same state.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from gabriel.logging_config import get_logger

logger = get_logger(__name__)

# Default seconds a paused tool call waits for a human decision before it is
# treated as an implicit denial (keeps stream connections from hanging forever).
DEFAULT_APPROVAL_TIMEOUT = 300.0


@dataclass(frozen=True)
class ApprovalDecision:
    """A user's accept/deny decision for one pending tool call."""

    approved: bool
    deny_reason: str | None = None


@dataclass
class _Pending:
    event: asyncio.Event
    decision: ApprovalDecision | None = None


class ApprovalRegistry:
    """In-process rendezvous between a paused chat stream and an inbound
    approval decision.

    Keys are ``"{session_id}:{tool_name}"``. Only one pending approval per
    ``(session, tool)`` pair is tracked at a time — sufficient because the
    stream pauses on each confirmation-gated call before issuing the next.
    """

    def __init__(self) -> None:
        self._pending: dict[str, _Pending] = {}

    @staticmethod
    def _key(session_id: str, tool_name: str) -> str:
        return f"{session_id}:{tool_name}"

    def register(self, session_id: str, tool_name: str) -> str:
        """Register a pending approval and return its key."""
        key = self._key(session_id, tool_name)
        self._pending[key] = _Pending(event=asyncio.Event())
        return key

    async def wait(
        self, key: str, *, timeout: float = DEFAULT_APPROVAL_TIMEOUT
    ) -> ApprovalDecision:
        """Block until a decision arrives for *key* (or *timeout* elapses).

        On timeout the pending entry is cleared and an implicit denial is
        returned so the stream can resume cleanly.
        """
        pending = self._pending.get(key)
        if pending is None:  # pragma: no cover - defensive
            return ApprovalDecision(approved=False, deny_reason="No pending approval.")
        try:
            await asyncio.wait_for(pending.event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Tool approval timed out for %s", key)
            self._pending.pop(key, None)
            return ApprovalDecision(
                approved=False, deny_reason="Approval timed out; treated as denied."
            )
        decision = pending.decision or ApprovalDecision(
            approved=False, deny_reason="No decision recorded."
        )
        self._pending.pop(key, None)
        return decision

    def resolve(
        self, session_id: str, tool_name: str, decision: ApprovalDecision
    ) -> bool:
        """Record *decision* for a pending ``(session, tool)`` and wake the
        waiting stream.

        Returns ``True`` if a matching pending approval existed.
        """
        key = self._key(session_id, tool_name)
        pending = self._pending.get(key)
        if pending is None:
            return False
        pending.decision = decision
        pending.event.set()
        return True

    def has_pending(self, session_id: str, tool_name: str) -> bool:
        return self._key(session_id, tool_name) in self._pending
