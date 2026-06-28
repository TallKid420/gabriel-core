from gabriel.runtime.contract import AgentRuntime
from gabriel.runtime.exceptions import RuntimeNotFoundError

from typing import Dict

class RuntimeRegistry:
    def __init__(self):
        self._runtimes: Dict[str, AgentRuntime] = {}

    def register(self, runtime: AgentRuntime):
        self._runtimes[runtime.name] = runtime

    def get(self, name: str) -> AgentRuntime:
        if name not in self._runtimes:
            raise RuntimeNotFoundError(f"No runtime registered with name: {name}")
        return self._runtimes[name]
        
# Global instance
runtime_registry = RuntimeRegistry()