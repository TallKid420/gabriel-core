"""Declarative deployment contract for Gabriel agents."""

from typing import Any

from pydantic import BaseModel, Field

from gabriel.agent.triggers import Trigger


class AgentSpecification(BaseModel):
    """Deployment-time contract that describes an agent.

    Agents do not execute without a specification.
    """

    name: str
    description: str = ""
    runtime: str
    model: str
    system_prompt: str = ""
    capabilities: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    memory_layers: list[str] = Field(default_factory=list)
    triggers: list[Trigger | str] = Field(default_factory=list)
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