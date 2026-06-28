from gabriel.runtime.contract import AgentRuntime
from gabriel.runtime.execution import ExecutionResult

class MockRuntime(AgentRuntime):
    @property
    def name(self):
        return "mock"
    
        async def execute(self, request) -> ExecutionResult:
            return ExecutionResult(
                sucess=True,
                output={"answer": "I am a mock response"},
                metrics={"duration": 0.1}
            )