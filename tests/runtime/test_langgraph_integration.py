import pytest

pytest.importorskip("langgraph")

from gabriel.runtime.execution import AgentExecutor, Execution
from gabriel.runtime.registry import register_default_runtimes
from gabriel.agent.models import Agent
from gabriel.agent.specification import AgentSpecification
from gabriel.resource.grn import GRN

@pytest.mark.asyncio
async def test_langgraph_execution_flow(execution_context):
    from gabriel.events.event_store import EventStore
    from gabriel.events.dispatcher import Dispatcher
    from gabriel.runtime.registry import RuntimeRegistry  # fresh instance

    dispatcher = Dispatcher(event_store=EventStore())
    fresh_registry = RuntimeRegistry()  # NOT the global runtime_registry
    register_default_runtimes(fresh_registry, dispatcher=dispatcher)

    executor = AgentExecutor(fresh_registry)  # use fresh_registry here too

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

    result_execution = await executor.run(execution)

    if result_execution.error:
        print(result_execution.error)

    assert result_execution.state.value == "completed"