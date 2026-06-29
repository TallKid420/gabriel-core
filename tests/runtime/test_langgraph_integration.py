import pytest

pytest.importorskip("langgraph")

from gabriel.runtime.execution import AgentExecutor
from gabriel.runtime.execution import Execution
from gabriel.runtime.registry import runtime_registry, register_default_runtimes
from gabriel.agent.models import Agent
from gabriel.agent.specification import AgentSpecification
from gabriel.resource.grn import GRN

@pytest.mark.asyncio
async def test_langgraph_execution_flow(execution_context):
    # Setup
    register_default_runtimes(runtime_registry)
    executor = AgentExecutor(runtime_registry)

    agent = Agent.create(
        grn=GRN.generate(org_id=execution_context.organization, resource_type="agent"),
        org_id=execution_context.organization,
        created_by="principal://org-123/system/deployer",
        specification=AgentSpecification(
            name="assistant",
            runtime="langgraph",
            model="gemini-3-flash",
        ),
    )

    context = execution_context
    context.metadata["runtime"] = "langgraph"
    context.metadata["agent"] = agent
    context.metadata["input"] = {"message": "hello"}
    execution = Execution(context=context)
    
    # Run
    result_execution = await executor.run(execution)
    
    # Assertions
    assert result_execution.state.value == "completed"
    assert "history" in result_execution.result.output
    assert result_execution.result.output["history"] == ["node_1_complete"]
    assert result_execution.result.output["org"] == execution_context.organization
    assert result_execution.result.output["model"] == "gemini-3-flash"