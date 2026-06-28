from gabriel.runtime.contract import AgentRuntime
from gabriel.runtime.execution import ExecutionMetrics, ExecutionResult

class MockRuntime(AgentRuntime):
    @property
    def name(self):
        return "mock"

    async def execute(self, request) -> ExecutionResult:
        return ExecutionResult(
            success=True,
            output={"answer": "I am a mock response", "agent": request.agent.specification.name},
            events=[],
            metrics=ExecutionMetrics(
                duration_ms=1.0,
                prompt_tokens=0,
                completion_tokens=0,
                tool_calls=0,
                memory_reads=0,
                memory_writes=0,
            ),
        )

    async def health(self):
        return {"status": "ok", "runtime": self.name}