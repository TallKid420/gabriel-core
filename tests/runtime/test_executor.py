import pytest

from gabriel.agent.models import Agent
from gabriel.agent.specification import AgentSpecification
from gabriel.resource.grn import GRN
from gabriel.runtime.execution import AgentExecutor, ExecutionMetrics, ExecutionRequest, ExecutionResult
from gabriel.runtime.mock_runtime import MockRuntime
from gabriel.runtime.registry import RuntimeRegistry


class RecordingRuntime(MockRuntime):
    def __init__(self):
        self.last_request = None

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.last_request = request
        return ExecutionResult(
            success=True,
            output={"echo": request.input.get("message", "")},
            events=[],
            metrics=ExecutionMetrics(
                duration_ms=2.0,
                prompt_tokens=5,
                completion_tokens=7,
                tool_calls=0,
                memory_reads=1,
                memory_writes=0,
            ),
        )


def _make_agent(org_id: str = "org-123") -> Agent:
    spec = AgentSpecification(name="assistant", runtime="mock", model="gpt-5")
    return Agent.create(
        grn=GRN.generate(org_id=org_id, resource_type="agent"),
        org_id=org_id,
        created_by="principal://org-123/user/admin",
        specification=spec,
    )


@pytest.mark.asyncio
async def test_executor_calls_runtime(execution_context) -> None:
    registry = RuntimeRegistry()
    runtime = RecordingRuntime()
    registry.register(runtime)

    executor = AgentExecutor(registry)
    request = ExecutionRequest(
        context=execution_context,
        agent=_make_agent(execution_context.organization),
        input={"message": "hi"},
        metadata={"runtime": "mock"},
    )

    result = await executor.execute(request)

    assert runtime.last_request is request
    assert result.success is True
    assert result.output["echo"] == "hi"


@pytest.mark.asyncio
async def test_runtime_metrics(execution_context) -> None:
    registry = RuntimeRegistry()
    registry.register(RecordingRuntime())

    executor = AgentExecutor(registry)
    request = ExecutionRequest(
        context=execution_context,
        agent=_make_agent(execution_context.organization),
        input={"message": "metrics"},
        metadata={"runtime": "mock"},
    )

    result = await executor.execute(request)

    assert result.metrics.duration_ms == 2.0
    assert result.metrics.prompt_tokens == 5
    assert result.metrics.completion_tokens == 7
