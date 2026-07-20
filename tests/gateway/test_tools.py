"""Runtime tool framework tests (Phase 3)."""
from __future__ import annotations

import json

import pytest

from gabriel.gateway.providers.base import ToolCallRequest
from gabriel.gateway.tools import (
    FunctionTool,
    RuntimeToolRegistry,
    UnknownToolError,
    build_default_tool_registry,
    execute_tool_call,
)


async def _echo(**kwargs):
    return {"echo": kwargs.get("text", "")}


def test_registry_register_get_and_duplicates():
    registry = RuntimeToolRegistry()
    tool = FunctionTool(_name="echo", _description="Echo back the input.", _fn=_echo)
    registry.register(tool)
    assert registry.get("echo") is tool
    assert registry.list_tools() == ["echo"]
    with pytest.raises(ValueError):
        registry.register(FunctionTool(_name="echo", _description="dup", _fn=_echo))
    with pytest.raises(UnknownToolError):
        registry.get("nope")


def test_llm_specs_shape_and_allowed_filter():
    registry = build_default_tool_registry()
    registry.register(
        FunctionTool(
            _name="echo",
            _description="Echo back the input.",
            _fn=_echo,
            _parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        )
    )
    specs = registry.llm_specs()
    names = {s["function"]["name"] for s in specs}
    assert {"echo", "calculate"} <= names
    assert all(s["type"] == "function" for s in specs)

    restricted = registry.llm_specs(allowed=["echo", "not-registered"])
    assert [s["function"]["name"] for s in restricted] == ["echo"]


@pytest.mark.asyncio
async def test_execute_tool_call_success():
    registry = build_default_tool_registry()
    call = ToolCallRequest(id="c1", name="calculate", arguments={"expression": "1 + 1"})
    result = await execute_tool_call(registry, call)
    assert result.success is True
    assert result.tool_call_id == "c1"
    payload = json.loads(result.content)
    assert "result" in payload
    message = result.to_message_dict()
    assert message["role"] == "tool"
    assert message["name"] == "calculate"


@pytest.mark.asyncio
async def test_execute_tool_call_unknown_tool_returns_error_result():
    registry = build_default_tool_registry()
    call = ToolCallRequest(id="c2", name="missing_tool", arguments={})
    result = await execute_tool_call(registry, call)
    assert result.success is False
    assert "missing_tool" in result.error


@pytest.mark.asyncio
async def test_execute_tool_call_respects_allowed_list():
    registry = build_default_tool_registry()
    call = ToolCallRequest(id="c3", name="calculate", arguments={"expression": "1"})
    result = await execute_tool_call(registry, call, allowed=["other_tool"])
    assert result.success is False
    assert "not allowed" in result.error


@pytest.mark.asyncio
async def test_execute_tool_call_captures_tool_exception():
    async def boom(**kwargs):
        raise RuntimeError("kaput")

    registry = RuntimeToolRegistry()
    registry.register(FunctionTool(_name="boom", _description="fails", _fn=boom))
    result = await execute_tool_call(
        registry, ToolCallRequest(id="c4", name="boom", arguments={})
    )
    assert result.success is False
    assert "kaput" in result.error
    assert json.loads(result.content) == {"error": "kaput"}


@pytest.mark.asyncio
async def test_function_tool_bridges_function_registry():
    from gabriel.tool.registry import function_registry

    binding = "test_gateway.echo"
    if not function_registry.is_registered(binding):
        function_registry.register(binding, _echo)

    tool = FunctionTool.from_function_registry(
        binding, description="Echo helper", name="echo_bridge"
    )
    assert tool.name == "echo_bridge"
    assert (await tool.run(text="hi")) == {"echo": "hi"}

