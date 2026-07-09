"""Tests for the legacy-agent-type specification templates (Phase 4)."""

import pytest

from gabriel.agent.capabilities import AgentCapability
from gabriel.agent.grn_bindings import is_tool_grn
from gabriel.agent.specification import AgentSpecification
from gabriel.agent.templates import (
    AGENT_TEMPLATES,
    build_specification,
    get_template,
    list_templates,
    template_vocabulary,
)
from gabriel.agent.validator import AgentValidator
from gabriel.memory.models import MemoryLayer


def test_all_legacy_types_have_templates() -> None:
    # Legacy taxonomy from agents/base_agent.py AGENT_TYPE_MAP + experimental types.
    assert set(list_templates()) == {"chat", "engineer", "researcher", "daemon", "server"}


def test_get_template_unknown_raises() -> None:
    with pytest.raises(KeyError):
        get_template("nope")


def test_chat_template_mirrors_legacy_chat_agent() -> None:
    spec = build_specification("chat")
    assert isinstance(spec, AgentSpecification)
    assert spec.name == "hermes-chat"
    assert spec.runtime == "langgraph"
    assert spec.provider == "ollama"
    # Legacy hermes-chat system prompt is preserved.
    assert "Hermes" in spec.system_prompt
    # Capabilities include CHAT + memory read/write + tool invoke.
    assert AgentCapability.CHAT.value in spec.capabilities
    assert AgentCapability.MEMORY_READ.value in spec.capabilities
    assert AgentCapability.MEMORY_WRITE.value in spec.capabilities
    assert AgentCapability.TOOL_INVOKE.value in spec.capabilities
    # Tools are GRN bindings.
    assert spec.tools, "chat template should bind tools"
    assert all(is_tool_grn(t) for t in spec.tools)
    # Memory config uses WORKING/SHORT_TERM/LONG_TERM.
    assert MemoryLayer.WORKING.value in spec.memory.read_layers
    assert MemoryLayer.SHORT_TERM.value in spec.memory.read_layers
    assert MemoryLayer.LONG_TERM.value in spec.memory.read_layers
    # Triggers include an API endpoint + user message event.
    event_types = [t.event_type for t in spec.normalized_triggers()]
    assert "UserMessageReceived" in event_types
    assert any(e.startswith("api:") for e in event_types)


def test_template_metadata_records_migration_provenance() -> None:
    spec = build_specification("engineer")
    assert spec.metadata["template"] == "engineer"
    assert spec.metadata["legacy_class"] == "EngineerAgent"
    assert "migrated_from" in spec.metadata


def test_build_overrides() -> None:
    spec = build_specification(
        "chat",
        name="custom-bot",
        model="gpt-5",
        system_prompt="You are custom.",
        extra_tools=["grn:*:tool/roll_dice:*"],
        metadata={"tier": "premium"},
    )
    assert spec.name == "custom-bot"
    assert spec.model == "gpt-5"
    assert spec.system_prompt == "You are custom."
    assert "grn:*:tool/roll_dice:*" in spec.tools
    assert spec.metadata["tier"] == "premium"


def test_daemon_is_event_driven() -> None:
    spec = build_specification("daemon")
    assert AgentCapability.EVENT_SUBSCRIBE.value in spec.capabilities
    event_types = [t.event_type for t in spec.normalized_triggers()]
    assert "DocumentIngested" in event_types


def test_server_template_is_minimal() -> None:
    spec = build_specification("server")
    assert spec.tools == []
    assert spec.memory.read_layers == [MemoryLayer.WORKING.value]


def test_every_template_builds_a_valid_spec() -> None:
    for key in list_templates():
        spec = build_specification(key)
        assert spec.name
        assert spec.runtime
        assert spec.model
        # memory_layers is the flat union used by the validator
        assert set(spec.memory_layers) == set(spec.memory.read_layers) | set(
            spec.memory.write_layers
        )


def test_templates_pass_validator_built_from_vocabulary() -> None:
    vocab = template_vocabulary()
    validator = AgentValidator(
        runtimes=vocab["runtimes"],
        tools=vocab["tools"],
        capabilities=vocab["capabilities"],
        memory_layers=vocab["memory_layers"],
        models=vocab["models"],
    )
    for key in list_templates():
        spec = build_specification(key)
        # Validator checks tool *names*; strip GRN wrappers first.
        checkable = spec.model_copy(update={"tools": spec.tool_names()})
        validator.validate(checkable)  # must not raise
