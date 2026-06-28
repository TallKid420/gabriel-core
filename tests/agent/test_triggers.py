import pytest

from gabriel.agent.deployment import AgentDeploymentService
from gabriel.agent.models import Agent
from gabriel.agent.specification import AgentSpecification
from gabriel.agent.triggers import Trigger
from gabriel.agent.validator import AgentValidator
from gabriel.events.event_store import EventStore
from gabriel.resource.registry import ResourceRegistry


@pytest.fixture
def validator() -> AgentValidator:
    return AgentValidator(
        runtimes=["langgraph"],
        tools=["search"],
        capabilities=["read_memory"],
        memory_layers=["session"],
        models=["gpt-5"],
    )


@pytest.fixture
def registry() -> ResourceRegistry:
    reg = ResourceRegistry()
    reg.register(Agent)
    return reg


@pytest.mark.asyncio
async def test_event_trigger_registration(
    validator: AgentValidator, registry: ResourceRegistry
) -> None:
    service = AgentDeploymentService(
        validator=validator,
        event_store=EventStore(),
        registry=registry,
    )

    spec = AgentSpecification(
        name="assistant",
        runtime="langgraph",
        model="gpt-5",
        triggers=[
            Trigger(event_type="UserMessageReceived", filter={"channel": "chat"})
        ],
    )

    agent = await service.deploy(
        specification=spec,
        org_id="org-123",
        created_by="principal://org-123/user/admin",
    )

    targets = service.triggers_for_event("UserMessageReceived")
    assert str(agent.grn) in targets


def test_invalid_trigger() -> None:
    with pytest.raises(ValueError):
        Trigger(event_type="", filter={})
