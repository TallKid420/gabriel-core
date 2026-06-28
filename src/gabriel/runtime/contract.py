from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gabriel.runtime.execution import ExecutionRequest, ExecutionResult

class AgentRuntime(ABC):
    @abstractmethod
    async def execute(
        self,
        request: "ExecutionRequest"
    ) -> "ExecutionResult":
        """Execute the agent and return a standardized result."""

    @abstractmethod
    async def health(self):
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the identifier for this runtime (e.g., 'langgraph')."""
        pass