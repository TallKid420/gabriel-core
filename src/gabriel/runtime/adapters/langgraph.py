from typing import Any, TypedDict
from langgraph.graph import END, StateGraph
from gabriel.runtime.contract import AgentRuntime
from gabriel.runtime.execution import ExecutionMetrics, ExecutionRequest, ExecutionResult
from gabriel.events.dispatcher import Dispatcher
from gabriel.events.event import Event


class LangGraphAdapter(AgentRuntime):
    """Bridges Gabriel's Execution model to LangGraph's Graph model."""

    def __init__(self, dispatcher: Dispatcher):
        # Inject the Dispatcher so nodes can emit events
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

        # Pass ExecutionContext into LangGraph config so nodes can access it
        config = {
            "configurable": {
                "gabriel_context": request.context,
                "gabriel_dispatcher": self.dispatcher,
            }
        }

        raw_result = await runnable.ainvoke(inputs, config=config)

        steps = len(raw_result.get("history", []))
        return ExecutionResult(
            success=True,
            output=raw_result,
            events=[],
            metrics=ExecutionMetrics(
                duration_ms=float(steps),
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
        config: dict,
    ) -> "_LangGraphState":
        """Main node. Emits a NodeCompleted event via the Dispatcher."""
        context = config["configurable"]["gabriel_context"]
        dispatcher = config["configurable"]["gabriel_dispatcher"]

        history = list(state.get("history", []))
        history.append("node_1_complete")

        # Emit event through the Dispatcher (your event bus)
        event = Event(
            type="agent.node_completed",
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