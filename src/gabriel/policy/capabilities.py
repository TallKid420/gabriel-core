"""Action -> Capability mapping for PEEL identity-based enforcement.

This module lives in **Core (Platform Layer)**.

PEEL has two complementary enforcement mechanisms:

1. Identity-based (capability) enforcement — the principal must hold the
   capability required by the action. This is fast, deterministic, and works
   without any org-level policy being configured (fail-secure default).
2. Policy-based enforcement — explicit ALLOW/DENY statements evaluated by the
   PolicyEngine. Explicit DENY always wins ("Explicit Deny Wins").

This file owns mechanism (1): a single, declarative mapping from an action
verb (e.g. ``resource:create``) to the capability a principal must hold.

It must NOT contain UI, LLM, or chat logic.
"""
from __future__ import annotations

from gabriel.identity.models import Capability


# Canonical mapping of action verbs to the capability required to perform them.
# Actions are namespaced as "<domain>:<verb>" and align with the
# ``action_name`` values dispatched by the API routers.
ACTION_CAPABILITY_MAP: dict[str, Capability] = {
    # Resource lifecycle
    "resource:create": Capability.WRITE_RESOURCE,
    "resource:update": Capability.WRITE_RESOURCE,
    "resource:delete": Capability.WRITE_RESOURCE,
    "resource:read": Capability.READ_RESOURCE,
    # Agents
    "agent:create": Capability.WRITE_RESOURCE,
    "agent:execute": Capability.EXECUTE_WORKFLOW,
    "agent:disable": Capability.WRITE_RESOURCE,
    "agent:enable": Capability.WRITE_RESOURCE,
    "agent:read": Capability.READ_RESOURCE,
    # Memory
    "memory:write": Capability.WRITE_RESOURCE,
    "memory:delete": Capability.WRITE_RESOURCE,
    "memory:read": Capability.READ_RESOURCE,
    # Documents (ingestion)
    "document:create": Capability.WRITE_RESOURCE,
    "document:ingest": Capability.WRITE_RESOURCE,
    "document:read": Capability.READ_RESOURCE,
    # Principals / identity administration
    "identity:create_principal": Capability.MANAGE_PRINCIPALS,
    "identity:suspend_principal": Capability.MANAGE_PRINCIPALS,
    "identity:read": Capability.READ_PRINCIPAL,
    # Organization
    "organization:read": Capability.READ_ORGANIZATION,
    # Policy administration
    "policy:create": Capability.MANAGE_POLICIES,
    "policy:update": Capability.MANAGE_POLICIES,
    "policy:delete": Capability.MANAGE_POLICIES,
}


def required_capability_for_action(action: str) -> Capability | None:
    """Return the capability required for ``action``.

    Args:
        action: The action verb, e.g. ``"resource:create"``.

    Returns:
        The required :class:`Capability`, or ``None`` if the action is not
        governed by a capability requirement (it will then be governed solely
        by explicit policy statements).
    """
    if action in ACTION_CAPABILITY_MAP:
        return ACTION_CAPABILITY_MAP[action]

    # Fall back to a coarse verb-based heuristic so unknown but well-formed
    # actions still fail secure rather than slipping through ungoverned.
    verb = action.split(":", 1)[-1].lower() if ":" in action else action.lower()
    if verb in {"read", "get", "list", "describe"}:
        return Capability.READ_RESOURCE
    if verb in {"create", "update", "delete", "write", "disable", "enable"}:
        return Capability.WRITE_RESOURCE
    if verb in {"execute", "run", "invoke"}:
        return Capability.EXECUTE_WORKFLOW
    return None
