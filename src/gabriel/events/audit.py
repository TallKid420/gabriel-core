from __future__ import annotations

from gabriel.events.event import Event


class AuditEvent(Event):
    """Base event for auditable security and policy actions."""

    type: str = "audit_event"


class PeelEvaluationEvent(AuditEvent):
    """Emitted whenever PEEL evaluates a request (allow or deny)."""

    type: str = "peel_evaluation"


class PolicyChangeEvent(AuditEvent):
    """Emitted when policy definitions are changed."""

    type: str = "policy_changed"


__all__ = ["AuditEvent", "PeelEvaluationEvent", "PolicyChangeEvent"]
