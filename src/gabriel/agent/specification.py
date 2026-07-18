"""Declarative deployment contract for Gabriel agents."""

from __future__ import annotations

from pydantic import BaseModel, Field

from gabriel.agent.capabilities import to_runtime_capabilities
from gabriel.agent.grn_bindings import resolve_tools, tool_name
from gabriel.agent.memory import MemoryRequirements
from gabriel.agent.runtime_config import RuntimeConfiguration
from gabriel.agent.triggers import Trigger


class AgentSpecification(BaseModel):
    """Deployment-time contract that describes an agent.

    Agents do not execute without a specification. A specification is fully
    declarative: it names the runtime and model, the capabilities the agent is
    designed to use, the tools it may invoke (as GRN bindings), the memory
    layers it operates over, and the triggers that activate it.

    Optional structured fields (``provider``, ``runtime_config``, ``memory``)
    were added in Phase 4 (agent migration) to carry the tuning knobs that
    legacy Gabriel agents declared in ``agents.yaml``. They all default to
    empty/``None`` so pre-existing specifications remain valid.
    """

    name: str
    description: str = ""
    runtime: str
    model: str
    provider: str = ""
    system_prompt: str = ""
    capabilities: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    disabled_tools: list[str] = Field(default_factory=list)
    knowledge_sources: list[str] = Field(default_factory=list)
    document_collections: list[str] = Field(default_factory=list)
    memory_layers: list[str] = Field(default_factory=list)
    triggers: list[Trigger | str] = Field(default_factory=list)
    runtime_config: RuntimeConfiguration | None = None
    memory: MemoryRequirements | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    def normalized_triggers(self) -> list[Trigger]:
        """Return triggers normalized as Trigger objects."""
        normalized: list[Trigger] = []
        for item in self.triggers:
            if isinstance(item, Trigger):
                normalized.append(item)
            else:
                normalized.append(Trigger(event_type=item, filter={}))
        return normalized

    def tool_names(self) -> list[str]:
        """Return the bare tool slugs, stripping any GRN binding wrapper."""
        return [tool_name(t) for t in self.tools]

    def disabled_tool_names(self) -> list[str]:
        """Return the bare disabled-tool slugs, stripping any GRN wrapper."""
        return [tool_name(t) for t in self.disabled_tools]

    def effective_tool_names(self) -> list[str]:
        """Enabled tool slugs for this agent: declared tools minus disabled.

        ``disabled_tools`` always wins over ``tools`` (explicit-deny-wins,
        mirroring PEEL semantics — ADR-008). An agent that declares no tools
        returns an empty list; the chat runtime interprets that as
        "all registered runtime tools minus disabled".
        """
        disabled = set(self.disabled_tool_names())
        return [name for name in self.tool_names() if name not in disabled]

    def grounding_source_grns(self) -> list[str]:
        """All knowledge GRNs the agent may ground on (knowledge + documents).

        Knowledge sources and document collections are both KnowledgeSource
        resources (typed variants); agents reference them purely by GRN.
        """
        seen: set[str] = set()
        combined: list[str] = []
        for grn in [*self.knowledge_sources, *self.document_collections]:
            if grn not in seen:
                seen.add(grn)
                combined.append(grn)
        return combined

    def resolved_tools(self, org_id: str, version: int = 1) -> list[str]:
        """Resolve (wildcard) tool bindings to concrete GRNs for *org_id*."""
        return resolve_tools(self.tools, org_id, version)

    def runtime_capabilities(self) -> list[str]:
        """Lower declared capabilities to runtime execution capability slugs."""
        return to_runtime_capabilities(self.capabilities)

    def effective_runtime_config(self) -> RuntimeConfiguration:
        """Return the runtime configuration, defaulting to the declared runtime."""
        if self.runtime_config is not None:
            return self.runtime_config
        return RuntimeConfiguration(runtime=self.runtime)
