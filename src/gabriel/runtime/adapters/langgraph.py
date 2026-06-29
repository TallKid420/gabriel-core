from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from gabriel.runtime.contract import AgentRuntime
from gabriel.runtime.execution import ExecutionMetrics, ExecutionRequest, ExecutionResult

class LangGraphAdapter(AgentRuntime):
    """Bridges Gabriel's Execution model to LangGraph's Graph model."""

    @property
    def name(self) -> str:
        return "langgraph"

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        # 1. Compile graph (Milestone: simple linear graph)
        graph = self._build_graph()
        runnable = graph.compile()

        # 2. Inject Gabriel context into config
        inputs: dict[str, Any] = {
            "input": request.input,
            "history": [],
            "model": request.agent.specification.model,
            "org": request.context.organization,
        }

        # 3. Run the graph
        raw_result = await runnable.ainvoke(inputs)

        # 4. Map to standardized Gabriel result
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
    ) -> "_LangGraphState":
        """A standard node that knows how to talk to Gabriel."""
        history = list(state.get("history", []))
        history.append("node_1_complete")

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