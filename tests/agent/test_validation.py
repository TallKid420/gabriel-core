import pytest

from gabriel.agent.exceptions import AgentValidationError
from gabriel.agent.specification import AgentSpecification
from gabriel.agent.triggers import Trigger
from gabriel.agent.validator import AgentValidator


@pytest.fixture
def validator() -> AgentValidator:
    return AgentValidator(
        runtimes=["langgraph", "dspy"],
        tools=["search", "calculator"],
        capabilities=["read_memory", "invoke_tool"],
        memory_layers=["session", "org"],
        models=["gpt-5", "gemini-3-flash"],
    )


def test_missing_runtime(validator: AgentValidator) -> None:
    spec = AgentSpecification(name="assistant", runtime="unknown", model="gpt-5")
    with pytest.raises(AgentValidationError):
        validator.validate(spec)


def test_unknown_tool(validator: AgentValidator) -> None:
    spec = AgentSpecification(
        name="assistant",
        runtime="langgraph",
        model="gpt-5",
        tools=["unknown_tool"],
    )
    with pytest.raises(AgentValidationError):
        validator.validate(spec)


def test_unknown_capability(validator: AgentValidator) -> None:
    spec = AgentSpecification(
        name="assistant",
        runtime="langgraph",
        model="gpt-5",
        capabilities=["root_access"],
    )
    with pytest.raises(AgentValidationError):
        validator.validate(spec)


def test_unknown_memory_layer(validator: AgentValidator) -> None:
    spec = AgentSpecification(
        name="assistant",
        runtime="langgraph",
        model="gpt-5",
        memory_layers=["global"],
    )
    with pytest.raises(AgentValidationError):
        validator.validate(spec)


def test_invalid_trigger(validator: AgentValidator) -> None:
    spec = AgentSpecification(
        name="assistant",
        runtime="langgraph",
        model="gpt-5",
        triggers=[Trigger(event_type="UserMessageReceived", filter={})],
    )
    validator.validate(spec)
