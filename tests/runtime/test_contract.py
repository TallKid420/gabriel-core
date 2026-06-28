import pytest

from gabriel.agent.models import Agent
from gabriel.agent.specification import AgentSpecification
from gabriel.resource.grn import GRN
from gabriel.runtime.execution import ExecutionMetrics, ExecutionRequest, ExecutionResult


def _make_agent(org_id: str = "org-123") -> Agent:
    spec = AgentSpecification(name="assistant", runtime="mock", model="gpt-5")
    return Agent.create(
        grn=GRN.generate(org_id=org_id, resource_type="agent"),
        org_id=org_id,
        created_by="principal://org-123/user/admin",
        specification=spec,
    )


def test_execution_result() -> None:
    result = ExecutionResult(
        success=True,
        output={"answer": "ok"},
        events=[],
        metrics=ExecutionMetrics(
            duration_ms=5.0,
            prompt_tokens=10,
            completion_tokens=20,
            tool_calls=1,
            memory_reads=2,
            memory_writes=1,
        ),
    )

    assert result.success is True
    assert result.output["answer"] == "ok"
    assert result.metrics.duration_ms == 5.0


def test_request_serialization(execution_context) -> None:
    request = ExecutionRequest(
        context=execution_context,
        agent=_make_agent(execution_context.organization),
        input={"message": "hello"},
        metadata={"runtime": "mock"},
    )

    payload = request.to_dict()

    assert payload["context"]["organization"] == execution_context.organization
    assert payload["agent"]["specification"]["name"] == "assistant"
    assert payload["input"]["message"] == "hello"
