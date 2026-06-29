# src/gabriel/runtime/adapters/langgraph.py

import time
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from gabriel.runtime.contract import AgentRuntime
from gabriel.runtime.execution import ExecutionMetrics, ExecutionRequest, ExecutionResult
from gabriel.events.dispatcher import Dispatcher
from gabriel.events.event import Event


class LangGraphAdapter(AgentRuntime):
    """Bridges Gabriel's Execution model to LangGraph's StateGraph model.

    The Dispatcher is injected at construction time and passed through
    LangGraph's config dict to each node. This avoids instance-level
    mutable state and makes concurrent executions safe.
    """

    def __init__(self, dispatcher: Dispatcher) -> None:
        self.dispatcher = dispatcher

    @property
    def name(self) -> str:
        return "langgraph"

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        graph = self._build_graph()
        runnable = graph.compile()

        inputs: dict[str, Any] = {
            "input": request.input,
            "history": [],
            "model": request.agent.specification.model,
            "org": request.context.organization,
        }

        # Pass ExecutionContext and Dispatcher through LangGraph config.
        # Nodes must read from config — never from adapter instance state —
        # so that concurrent executions do not interfere with each other.
        config = {
            "configurable": {
                "gabriel_context": request.context,
                "gabriel_dispatcher": self.dispatcher,
            }
        }

        start = time.monotonic()
        raw_result = await runnable.ainvoke(inputs, config=config)
        duration_ms = (time.monotonic() - start) * 1000.0

        return ExecutionResult(
            success=True,
            output=raw_result,
            # Events are published to the Dispatcher stream during execution.
            # They are not collected here. Consumers should subscribe to the
            # Dispatcher before invoking execute() if they need real-time events.
            events=[],
            metrics=ExecutionMetrics(
                duration_ms=duration_ms,
                prompt_tokens=0,
                completion_tokens=0,
                tool_calls=0,
                memory_reads=0,
                memory_writes=0,
            ),
        )

    async def health(self) -> dict[str, str]:
        return {"status": "ok", "runtime": self.name}

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(_LangGraphState)
        builder.add_node("gabriel_node", self.gabriel_node)
        builder.set_entry_point("gabriel_node")
        builder.add_edge("gabriel_node", END)
        return builder

    async def gabriel_node(
        self,
        state: "_LangGraphState",
        config: RunnableConfig | None = None,
    ) -> "_LangGraphState":
        """Primary execution node. Emits a NodeCompleted event via the Dispatcher.

        Context and Dispatcher are read exclusively from the LangGraph config dict.
        Never read from adapter instance state — doing so would break concurrent
        execution safety.
        """
        configurable = (config or {}).get("configurable", {})
        context = configurable.get("gabriel_context")
        dispatcher = configurable.get("gabriel_dispatcher")

        if context is None:
            raise ValueError(
                "gabriel_context is missing from LangGraph config. "
                "ExecutionContext must be passed via config['configurable']['gabriel_context']."
            )
        if dispatcher is None:
            raise ValueError(
                "gabriel_dispatcher is missing from LangGraph config. "
                "Dispatcher must be passed via config['configurable']['gabriel_dispatcher']."
            )

        history = list(state.get("history", []))
        history.append("node_1_complete")

        event = Event(
            type="agent.node_completed",
            principal_id=str(context.principal.id),
            organization_id=context.organization,
            payload={"node": "gabriel_node"},
        )
        await dispatcher.publish(event)

        return {
            "input": state.get("input", {}),
            "history": history,
            "model": state.get("model", ""),
            "org": state.get("org", ""),
        }


class _LangGraphState(TypedDict, total=False):
    input: dict[str, Any]
    history: list[str]
    model: str
    org: str