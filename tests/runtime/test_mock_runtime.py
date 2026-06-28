import pytest

from gabriel.agent.models import Agent
from gabriel.agent.specification import AgentSpecification
from gabriel.resource.grn import GRN
from gabriel.runtime.execution import ExecutionRequest
from gabriel.runtime.mock_runtime import MockRuntime


def _make_agent(org_id: str = "org-123") -> Agent:
    spec = AgentSpecification(name="assistant", runtime="mock", model="gpt-5")
    return Agent.create(
        grn=GRN.generate(org_id=org_id, resource_type="agent"),
        org_id=org_id,
        created_by="principal://org-123/user/admin",
        specification=spec,
    )


@pytest.mark.asyncio
async def test_health() -> None:
    runtime = MockRuntime()

    health = await runtime.health()

    assert health["status"] == "ok"
    assert health["runtime"] == "mock"


@pytest.mark.asyncio
async def test_execution_result(execution_context) -> None:
    runtime = MockRuntime()
    request = ExecutionRequest(
        context=execution_context,
        agent=_make_agent(execution_context.organization),
        input={"message": "hello"},
        metadata={"runtime": "mock"},
    )

    result = await runtime.execute(request)

    assert result.success is True
    assert "answer" in result.output
