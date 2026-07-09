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
