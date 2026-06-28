import pytest

from gabriel.agent.deployment import AgentDeploymentService
from gabriel.agent.models import Agent
from gabriel.agent.specification import AgentSpecification
from gabriel.agent.validator import AgentValidator
from gabriel.events.event_store import EventStore
from gabriel.resource.registry import ResourceRegistry


@pytest.fixture
def registry() -> ResourceRegistry:
    reg = ResourceRegistry()
    reg.register(Agent)
    return reg


@pytest.fixture
def validator() -> AgentValidator:
    return AgentValidator(
        runtimes=["langgraph"],
        tools=["search"],
        capabilities=["read_memory"],
        memory_layers=["session"],
        models=["gpt-5"],
    )


@pytest.mark.asyncio
async def test_deploy_agent(registry: ResourceRegistry, validator: AgentValidator) -> None:
    service = AgentDeploymentService(
        validator=validator,
        event_store=EventStore(),
        registry=registry,
    )

    spec = AgentSpecification(
        name="assistant",
        runtime="langgraph",
        model="gpt-5",
        system_prompt="Be concise.",
    )

    agent = await service.deploy(
        specification=spec,
        org_id="org-123",
        created_by="principal://org-123/user/admin",
    )

    assert agent.resource_type.value == "agent"
    assert registry.get("agent") is Agent


@pytest.mark.asyncio
async def test_agent_created_event_emitted(
    registry: ResourceRegistry, validator: AgentValidator
) -> None:
    event_store = EventStore()
    service = AgentDeploymentService(
        validator=validator,
        event_store=event_store,
        registry=registry,
    )

    spec = AgentSpecification(name="assistant", runtime="langgraph", model="gpt-5")
    await service.deploy(
        specification=spec,
        org_id="org-123",
        created_by="principal://org-123/user/admin",
    )

    events = event_store.events_by_type("AgentCreated")
    assert len(events) == 1
    assert events[0].payload["name"] == "assistant"
