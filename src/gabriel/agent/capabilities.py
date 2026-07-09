"""Agent capability declaration models.

Capabilities describe *what an agent is designed to do*. They are declared on
an :class:`~gabriel.agent.specification.AgentSpecification` at deployment time.
PEEL (the Policy Enforcement Execution Layer) is the authority that decides
whether a granted capability may actually be exercised against a concrete
resource at runtime — see ADR-019 (Zero Trust Runtime).

The :class:`AgentCapability` enum is the canonical vocabulary used by the
migration templates (Phase 4). It intentionally maps onto the lower-level
runtime/identity capability enums so an ``AgentSpecification`` can be lowered
into an execution context:

    AgentCapability            runtime.Capability / identity.Capability
    -------------------------  ----------------------------------------
    CHAT                       execute_agent / execute_workflow
    MEMORY_READ                read_memory
    MEMORY_WRITE               write_memory
    MEMORY_PROMOTE             write_memory
    TOOL_INVOKE                invoke_tool / call_tool
    FILE_READ                  file_read
    FILE_WRITE                 file_write
    INTEGRATION_READ           call_tool
    EVENT_SUBSCRIBE            create_event
    SCHEDULE                   schedule_execution
    STREAM                     execute_agent
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class AgentCapability(str, Enum):
    """Canonical capability vocabulary declared by agent specifications.

    Values are stable lowercase slugs so they persist cleanly to JSON/YAML and
    round-trip through :class:`AgentSpecification`.
    """

    # Conversation / execution
    CHAT = "chat"
    """Agent can carry on an interactive conversation with a principal."""

    STREAM = "stream"
    """Agent can stream partial/token-level output back to the caller."""

    # Memory operations (multi-layer memory architecture, ADR-012)
    MEMORY_READ = "memory_read"
    """Agent can read from its configured memory layers."""

    MEMORY_WRITE = "memory_write"
    """Agent can persist new entries into its configured memory layers."""

    MEMORY_PROMOTE = "memory_promote"
    """Agent can promote memories between layers (working -> long-term …)."""

    # Tool / capability separation (ADR-016)
    TOOL_INVOKE = "tool_invoke"
    """Agent can invoke registered tools through the ToolExecutor."""

    # File / document access
    FILE_READ = "file_read"
    """Agent can read org-scoped files/documents via file tools."""

    FILE_WRITE = "file_write"
    """Agent can write org-scoped files/documents via file tools."""

    # External integrations (email, calendar, …)
    INTEGRATION_READ = "integration_read"
    """Agent can read from connected external integrations."""

    INTEGRATION_WRITE = "integration_write"
    """Agent can write/act on connected external integrations."""

    # Event-driven execution (ADR-017)
    EVENT_SUBSCRIBE = "event_subscribe"
    """Agent can be activated by platform events (daemon-style)."""

    SCHEDULE = "schedule"
    """Agent can be scheduled to run on a recurring/temporal trigger."""

    @classmethod
    def values(cls) -> list[str]:
        """Return the list of all capability slug values."""
        return [c.value for c in cls]


# Mapping from the agent-domain capability vocabulary to the runtime
# execution capability slugs (gabriel.runtime.capabilities.Capability values).
# Used when lowering a specification into an ExecutionContext.
AGENT_TO_RUNTIME_CAPABILITY: dict[str, str] = {
    AgentCapability.CHAT.value: "execute_agent",
    AgentCapability.STREAM.value: "execute_agent",
    AgentCapability.MEMORY_READ.value: "read_memory",
    AgentCapability.MEMORY_WRITE.value: "write_memory",
    AgentCapability.MEMORY_PROMOTE.value: "write_memory",
    AgentCapability.TOOL_INVOKE.value: "invoke_tool",
    AgentCapability.FILE_READ.value: "invoke_tool",
    AgentCapability.FILE_WRITE.value: "invoke_tool",
    AgentCapability.INTEGRATION_READ.value: "invoke_tool",
    AgentCapability.INTEGRATION_WRITE.value: "invoke_tool",
    AgentCapability.EVENT_SUBSCRIBE.value: "create_event",
    AgentCapability.SCHEDULE.value: "schedule_execution",
}


def to_runtime_capabilities(capabilities: list[str]) -> list[str]:
    """Lower agent-domain capability slugs to runtime capability slugs.

    Unknown capabilities are passed through unchanged so custom capabilities
    are never silently dropped.
    """
    lowered: list[str] = []
    for cap in capabilities:
        lowered.append(AGENT_TO_RUNTIME_CAPABILITY.get(cap, cap))
    # de-duplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for cap in lowered:
        if cap not in seen:
            seen.add(cap)
            result.append(cap)
    return result


class AgentCapabilities(BaseModel):
    """Requested capabilities. PEEL determines what is granted."""

    requested: set[str] = Field(default_factory=set)

    model_config = {"frozen": True}
