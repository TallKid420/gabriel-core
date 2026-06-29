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


def register_default_runtimes(
    registry: RuntimeRegistry | None = None,
    dispatcher=None,
) -> RuntimeRegistry:
    """Register built-in runtimes into the target registry.

        Args:
            registry: Target registry. Defaults to the module-level runtime_registry.
                    Tests should always pass an explicit registry instance.
            dispatcher: Dispatcher instance required by LangGraphAdapter.
                        Must be provided if LangGraph is installed. Passing None
                        when langgraph is available will raise ValueError.

        Returns:
            The registry that was populated.

        Notes:
            DuplicateRuntimeError is suppressed intentionally — calling this function
            more than once on the same registry is safe and idempotent.
    """
    target = registry or runtime_registry

    try:
        from gabriel.runtime.mock_runtime import MockRuntime
        target.register(MockRuntime())
    except DuplicateRuntimeError:
        pass

    try:
        from gabriel.runtime.adapters.langgraph import LangGraphAdapter

        if dispatcher is None:
            raise ValueError(
                "Dispatcher must be provided when registering LangGraphAdapter."
                "Pass dispatcher=<your_dispatcher> to register_default_runtimes()."
            )
        
        target.register(LangGraphAdapter(dispatcher=dispatcher))
    except DuplicateRuntimeError:
        pass
    except ImportError:
        # langgraph not installed — skip silently, this runtime is optional
        pass

    return target