import pytest

from gabriel.agent.specification import AgentSpecification
from gabriel.agent.triggers import Trigger


def test_valid_spec() -> None:
    spec = AgentSpecification(
        name="assistant",
        runtime="langgraph",
        model="gpt-5",
        system_prompt="You are helpful.",
        tools=["search"],
        capabilities=["read_memory"],
        memory_layers=["session"],
        triggers=[Trigger(event_type="UserMessageReceived", filter={})],
    )

    assert spec.name == "assistant"
    assert spec.runtime == "langgraph"
    assert spec.model == "gpt-5"


def test_trigger_string_normalization() -> None:
    spec = AgentSpecification(
        name="assistant",
        runtime="langgraph",
        model="gpt-5",
        triggers=["OrganizationCreated"],
    )

    normalized = spec.normalized_triggers()
    assert len(normalized) == 1
    assert normalized[0].event_type == "OrganizationCreated"


def test_invalid_trigger() -> None:
    with pytest.raises(ValueError):
        Trigger(event_type="", filter={})
