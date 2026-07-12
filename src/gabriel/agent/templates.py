"""Agent specification templates mirroring legacy Gabriel agent types.

Phase 4 (Agent Migration) deliverable.

Legacy Gabriel shipped a small taxonomy of agent *types* (``chat``, ``engineer``,
``researcher``, ``daemon``, ``server``) implemented as LangChain/LangGraph agents
and configured through ``config/agents.yaml`` + ``agents/base_agent.py``. Each
type baked in a fixed set of tools, a memory/checkpointer strategy, and an
activation pattern.

Gabriel Core replaces those imperative classes with declarative
:class:`~gabriel.agent.specification.AgentSpecification` documents. This module
provides a **template library**: one :class:`AgentTemplate` per legacy type that
knows how to emit a ready-to-deploy specification, capturing the legacy
capabilities, tool bindings (as GRNs), memory layers, and triggers.

Usage::

    from gabriel.agent.templates import AGENT_TEMPLATES, build_specification

    spec = build_specification("chat", name="hermes-chat", model="gpt-oss:120b")
    # -> AgentSpecification ready for AgentDeploymentService / AgentService

The mapping from legacy type -> template is intentionally 1:1 so the migration
is auditable against ``Legacy_Feature_Audit`` and the ADR compliance report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from gabriel.agent.capabilities import AgentCapability
from gabriel.agent.grn_bindings import tool_grn
from gabriel.agent.memory import MemoryRequirements
from gabriel.agent.runtime_config import RuntimeConfiguration
from gabriel.agent.specification import AgentSpecification
from gabriel.agent.triggers import Trigger
from gabriel.memory.models import MemoryLayer

# Default runtime + provider for migrated agents. Legacy agents ran on
# LangChain/LangGraph via Ollama; Core's LangGraph adapter is the target runtime.
DEFAULT_RUNTIME = "langgraph"
DEFAULT_PROVIDER = "ollama"


def _tools(*names: str) -> list[str]:
    """Build a list of template (wildcard) tool GRN bindings."""
    return [tool_grn(n) for n in names]


@dataclass(frozen=True)
class AgentTemplate:
    """A reusable blueprint for one legacy agent type.

    A template is org-agnostic. Calling :meth:`build` stamps out a concrete
    :class:`AgentSpecification` with optional per-instance overrides.
    """

    key: str
    """Legacy agent ``type`` slug (e.g. ``"chat"``)."""

    legacy_class: str
    """Legacy implementation class this template mirrors (audit trail)."""

    default_name: str
    description: str
    default_model: str
    system_prompt: str
    capabilities: list[str]
    tools: list[str]
    read_layers: list[str]
    write_layers: list[str]
    retention: str
    triggers: list[Trigger]
    runtime: str = DEFAULT_RUNTIME
    provider: str = DEFAULT_PROVIDER
    runtime_config: RuntimeConfiguration = field(
        default_factory=lambda: RuntimeConfiguration(runtime=DEFAULT_RUNTIME)
    )

    @property
    def memory_layers(self) -> list[str]:
        """Flat, de-duplicated list of every memory layer used (for validation)."""
        seen: dict[str, None] = {}
        for layer in [*self.read_layers, *self.write_layers]:
            seen.setdefault(layer, None)
        return list(seen)

    def build(
        self,
        *,
        name: str | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        provider: str | None = None,
        extra_tools: list[str] | None = None,
        metadata: dict[str, str] | None = None,
        runtime_config: RuntimeConfiguration | None = None,
    ) -> AgentSpecification:
        """Materialize this template into an :class:`AgentSpecification`."""
        tools = list(self.tools)
        if extra_tools:
            tools.extend(extra_tools)

        meta = {
            "template": self.key,
            "legacy_class": self.legacy_class,
            "migrated_from": "gabriel-legacy/config/agents.yaml",
        }
        if metadata:
            meta.update(metadata)

        return AgentSpecification(
            name=name or self.default_name,
            description=self.description,
            runtime=self.runtime,
            model=model or self.default_model,
            provider=provider or self.provider,
            system_prompt=self.system_prompt if system_prompt is None else system_prompt,
            capabilities=list(self.capabilities),
            tools=tools,
            memory_layers=self.memory_layers,
            triggers=list(self.triggers),
            runtime_config=runtime_config or self.runtime_config,
            memory=MemoryRequirements(
                read_layers=list(self.read_layers),
                write_layers=list(self.write_layers),
                retention=self.retention,
            ),
            metadata=meta,
        )


# ---------------------------------------------------------------------------
# Template definitions — one per legacy agent type
# ---------------------------------------------------------------------------

# CHAT — the live legacy agent (agents/types/chat_agent.py, "hermes-chat").
# Interactive assistant with conversational memory (LangGraph checkpointer) and
# a safe general-purpose toolbox.
CHAT_TEMPLATE = AgentTemplate(
    key="chat",
    legacy_class="ChatAgent",
    default_name="hermes-chat",
    description="Interactive conversational assistant migrated from the legacy ChatAgent.",
    default_model="gpt-oss:120b",
    system_prompt="You are Hermes, a personal assistant.",
    capabilities=[
        AgentCapability.CHAT.value,
        AgentCapability.STREAM.value,
        AgentCapability.MEMORY_READ.value,
        AgentCapability.MEMORY_WRITE.value,
        AgentCapability.TOOL_INVOKE.value,
    ],
    tools=_tools("get_time", "days_between", "calculate", "convert_units", "list_tools"),
    read_layers=[MemoryLayer.WORKING.value, MemoryLayer.SHORT_TERM.value, MemoryLayer.LONG_TERM.value],
    write_layers=[MemoryLayer.WORKING.value, MemoryLayer.SHORT_TERM.value],
    retention="session",
    triggers=[
        Trigger(event_type="UserMessageReceived", filter={}),
        Trigger(event_type="api:POST:/chat/send", filter={"channel": "chat"}),
    ],
    runtime_config=RuntimeConfiguration(
        runtime=DEFAULT_RUNTIME, temperature=0.0, max_tokens=10000, timeout_seconds=20
    ),
)

# ENGINEER — experimental legacy EngineerAgent. Coding/automation assistant with
# file access and computation tools; persistent long-term memory.
ENGINEER_TEMPLATE = AgentTemplate(
    key="engineer",
    legacy_class="EngineerAgent",
    default_name="engineer-1",
    description="Software-engineering assistant migrated from the legacy EngineerAgent.",
    default_model="gpt-oss:120b",
    system_prompt="You are an engineering assistant. Be precise and cite file references.",
    capabilities=[
        AgentCapability.CHAT.value,
        AgentCapability.MEMORY_READ.value,
        AgentCapability.MEMORY_WRITE.value,
        AgentCapability.TOOL_INVOKE.value,
        AgentCapability.FILE_READ.value,
        AgentCapability.FILE_WRITE.value,
    ],
    tools=_tools(
        "find_file", "search_documents", "semantic_search",
        "calculate", "convert_units", "hash_text", "get_time",
    ),
    read_layers=[
        MemoryLayer.WORKING.value, MemoryLayer.SHORT_TERM.value,
        MemoryLayer.LONG_TERM.value, MemoryLayer.PROCEDURAL.value,
    ],
    write_layers=[
        MemoryLayer.WORKING.value, MemoryLayer.SHORT_TERM.value,
        MemoryLayer.LONG_TERM.value,
    ],
    retention="persistent",
    triggers=[
        Trigger(event_type="UserMessageReceived", filter={}),
        Trigger(event_type="api:POST:/chat/send", filter={"channel": "engineer"}),
    ],
    runtime_config=RuntimeConfiguration(
        runtime=DEFAULT_RUNTIME, temperature=0.0, max_tokens=10000,
        timeout_seconds=60, max_iterations=25,
    ),
)

# RESEARCHER — experimental legacy ResearcherAgent. Runs research passes,
# reads documents/integrations, and can be scheduled.
RESEARCHER_TEMPLATE = AgentTemplate(
    key="researcher",
    legacy_class="ResearcherAgent",
    default_name="researcher-daily",
    description="Research assistant migrated from the legacy ResearcherAgent.",
    default_model="gpt-oss:120b",
    system_prompt="You are a research assistant. Gather, synthesize, and cite sources.",
    capabilities=[
        AgentCapability.CHAT.value,
        AgentCapability.MEMORY_READ.value,
        AgentCapability.MEMORY_WRITE.value,
        AgentCapability.MEMORY_PROMOTE.value,
        AgentCapability.TOOL_INVOKE.value,
        AgentCapability.FILE_READ.value,
        AgentCapability.INTEGRATION_READ.value,
        AgentCapability.SCHEDULE.value,
    ],
    tools=_tools(
        "semantic_search", "search_documents", "find_file",
        "get_current_weather", "get_time", "days_between",
    ),
    read_layers=[
        MemoryLayer.WORKING.value, MemoryLayer.SHORT_TERM.value,
        MemoryLayer.LONG_TERM.value, MemoryLayer.SEMANTIC.value,
    ],
    write_layers=[
        MemoryLayer.SHORT_TERM.value, MemoryLayer.LONG_TERM.value,
        MemoryLayer.SEMANTIC.value, MemoryLayer.ARCHIVAL.value,
    ],
    retention="persistent",
    triggers=[
        Trigger(event_type="ResearchRequested", filter={}),
        Trigger(event_type="schedule:cron", filter={"cron": "0 8 * * *"}),
    ],
    runtime_config=RuntimeConfiguration(
        runtime=DEFAULT_RUNTIME, temperature=0.0, max_tokens=8000,
        timeout_seconds=120, max_iterations=30,
    ),
)

# DAEMON — experimental legacy DaemonAgent. Long-lived, event-driven background
# worker (e.g. document ingestion pipeline reactions).
DAEMON_TEMPLATE = AgentTemplate(
    key="daemon",
    legacy_class="DaemonAgent",
    default_name="daemon-worker",
    description="Event-driven background worker migrated from the legacy DaemonAgent.",
    default_model="gpt-oss:20b",
    system_prompt="You are a background worker. React to platform events efficiently.",
    capabilities=[
        AgentCapability.EVENT_SUBSCRIBE.value,
        AgentCapability.MEMORY_READ.value,
        AgentCapability.MEMORY_WRITE.value,
        AgentCapability.TOOL_INVOKE.value,
        AgentCapability.FILE_READ.value,
    ],
    tools=_tools("find_file", "search_documents", "semantic_search", "get_time"),
    read_layers=[
        MemoryLayer.WORKING.value, MemoryLayer.EPISODIC.value,
        MemoryLayer.LONG_TERM.value,
    ],
    write_layers=[MemoryLayer.EPISODIC.value, MemoryLayer.LONG_TERM.value],
    retention="persistent",
    triggers=[
        Trigger(event_type="DocumentIngested", filter={}),
        Trigger(event_type="ResourceCreated", filter={"resource_type": "document"}),
    ],
    runtime_config=RuntimeConfiguration(
        runtime=DEFAULT_RUNTIME, temperature=0.0, max_tokens=4096,
        timeout_seconds=300, max_iterations=50,
    ),
)

# SERVER — experimental legacy ServerAgent. Minimal, stateless LLM endpoint with
# no tools and only working memory.
SERVER_TEMPLATE = AgentTemplate(
    key="server",
    legacy_class="ServerAgent",
    default_name="server",
    description="Stateless LLM completion agent migrated from the legacy ServerAgent.",
    default_model="gpt-oss:20b",
    system_prompt="",
    capabilities=[AgentCapability.CHAT.value, AgentCapability.STREAM.value],
    tools=[],
    read_layers=[MemoryLayer.WORKING.value],
    write_layers=[MemoryLayer.WORKING.value],
    retention="session",
    triggers=[Trigger(event_type="api:POST:/chat/send", filter={"channel": "server"})],
    runtime_config=RuntimeConfiguration(
        runtime=DEFAULT_RUNTIME, temperature=0.3, max_tokens=1024, timeout_seconds=20
    ),
)


AGENT_TEMPLATES: dict[str, AgentTemplate] = {
    t.key: t
    for t in (
        CHAT_TEMPLATE,
        ENGINEER_TEMPLATE,
        RESEARCHER_TEMPLATE,
        DAEMON_TEMPLATE,
        SERVER_TEMPLATE,
    )
}


def list_templates() -> list[str]:
    """Return the available template keys (legacy agent types)."""
    return list(AGENT_TEMPLATES)


def get_template(key: str) -> AgentTemplate:
    """Return the template for *key*.

    Raises:
        KeyError: if no template is registered under *key*.
    """
    try:
        return AGENT_TEMPLATES[key]
    except KeyError as exc:
        raise KeyError(
            f"Unknown agent template '{key}'. Available: {sorted(AGENT_TEMPLATES)}"
        ) from exc


def build_specification(key: str, **overrides) -> AgentSpecification:
    """Convenience: fetch template *key* and build a specification.

    Extra keyword arguments are forwarded to :meth:`AgentTemplate.build`.
    """
    return get_template(key).build(**overrides)


# Validator vocabulary derived from the template library. Handy when
# constructing an AgentValidator that must accept every migrated spec.
def template_vocabulary() -> dict[str, list[str]]:
    """Return the union of runtimes/tools/capabilities/memory-layers/models
    used across every template — suitable for seeding an ``AgentValidator``."""
    runtimes: set[str] = set()
    tools: set[str] = set()
    capabilities: set[str] = set()
    memory_layers: set[str] = set()
    models: set[str] = set()
    for template in AGENT_TEMPLATES.values():
        runtimes.add(template.runtime)
        capabilities.update(template.capabilities)
        memory_layers.update(template.memory_layers)
        models.add(template.default_model)
        spec = template.build()
        tools.update(spec.tool_names())
    return {
        "runtimes": sorted(runtimes),
        "tools": sorted(tools),
        "capabilities": sorted(capabilities),
        "memory_layers": sorted(memory_layers),
        "models": sorted(models),
    }
