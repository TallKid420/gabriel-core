"""Agent specification validation for deployment."""

from typing import Iterable

from gabriel.agent.exceptions import AgentValidationError
from gabriel.agent.specification import AgentSpecification


class AgentValidator:
    """Validates declarative AgentSpecification before deployment."""

    def __init__(
        self,
        runtimes: Iterable[str],
        tools: Iterable[str],
        capabilities: Iterable[str],
        memory_layers: Iterable[str],
        models: Iterable[str],
    ) -> None:
        self._runtimes = set(runtimes)
        self._tools = set(tools)
        self._capabilities = set(capabilities)
        self._memory_layers = set(memory_layers)
        self._models = set(models)

    def validate(self, specification: AgentSpecification) -> None:
        if specification.runtime not in self._runtimes:
            raise AgentValidationError(f"Unknown runtime: {specification.runtime}")

        if specification.model not in self._models:
            raise AgentValidationError(f"Unknown model: {specification.model}")

        unknown_tools = [tool for tool in specification.tools if tool not in self._tools]
        if unknown_tools:
            raise AgentValidationError(f"Unknown tool(s): {', '.join(sorted(unknown_tools))}")

        unknown_caps = [
            capability
            for capability in specification.capabilities
            if capability not in self._capabilities
        ]
        if unknown_caps:
            raise AgentValidationError(
                f"Unknown capability/capabilities: {', '.join(sorted(unknown_caps))}"
            )

        unknown_layers = [
            layer for layer in specification.memory_layers if layer not in self._memory_layers
        ]
        if unknown_layers:
            raise AgentValidationError(
                f"Unknown memory layer(s): {', '.join(sorted(unknown_layers))}"
            )

        for trigger in specification.normalized_triggers():
            if not trigger.event_type.strip():
                raise AgentValidationError("Invalid trigger: event_type is required")
