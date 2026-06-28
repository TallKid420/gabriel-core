from gabriel.runtime.contract import AgentRuntime
from gabriel.runtime.exceptions import RuntimeNotFoundError, DuplicateRuntimeError

from typing import Dict

class RuntimeRegistry:
    def __init__(self):
        self._runtimes: Dict[str, AgentRuntime] = {}

    def register(self, runtime: AgentRuntime):
        if runtime.name in self._runtimes:
            raise DuplicateRuntimeError(
                f"Runtime already registered with name: {runtime.name}"
            )
        self._runtimes[runtime.name] = runtime

    def get(self, name: str) -> AgentRuntime:
        if name not in self._runtimes:
            raise RuntimeNotFoundError(f"No runtime registered with name: {name}")
        return self._runtimes[name]

    def all(self) -> Dict[str, AgentRuntime]:
        return dict(self._runtimes)
        
# Global instance
runtime_registry = RuntimeRegistry()