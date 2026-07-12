"""Tests for GRN-based tool bindings (Phase 4 agent migration)."""

import pytest

from gabriel.agent.grn_bindings import (
    ToolBinding,
    is_tool_grn,
    parse_tool_grn,
    resolve_tools,
    tool_grn,
    tool_name,
)


def test_tool_grn_template_form() -> None:
    assert tool_grn("get_time") == "grn:*:tool/get_time:*"


def test_tool_grn_concrete_form() -> None:
    assert tool_grn("calculate", org_id="acme", version=2) == "grn:acme:tool/calculate:2"


def test_tool_grn_rejects_empty_name() -> None:
    with pytest.raises(ValueError):
        tool_grn("  ")


@pytest.mark.parametrize(
    "value,expected",
    [
        ("grn:*:tool/get_time:*", True),
        ("grn:acme:tool/get_time:1", True),
        ("grn:acme:agent/foo:1", False),  # not a tool
        ("get_time", False),  # bare slug
        ("grn:acme:tool/get_time", False),  # missing version
    ],
)
def test_is_tool_grn(value: str, expected: bool) -> None:
    assert is_tool_grn(value) is expected


def test_parse_tool_grn_roundtrip() -> None:
    binding = parse_tool_grn("grn:*:tool/get_time:*")
    assert binding == ToolBinding(name="get_time", org_id="*", version="*")
    assert binding.to_grn() == "grn:*:tool/get_time:*"


def test_parse_tool_grn_rejects_malformed() -> None:
    with pytest.raises(ValueError):
        parse_tool_grn("not-a-grn")


def test_binding_resolve_fills_wildcards() -> None:
    binding = parse_tool_grn("grn:*:tool/get_time:*")
    assert binding.resolve("acme", version=3) == "grn:acme:tool/get_time:3"


def test_binding_resolve_preserves_concrete_values() -> None:
    binding = parse_tool_grn("grn:root:tool/get_time:5")
    assert binding.resolve("acme", version=3) == "grn:root:tool/get_time:5"


def test_tool_name_accepts_grn_and_bare_slug() -> None:
    assert tool_name("grn:*:tool/get_time:*") == "get_time"
    assert tool_name("get_time") == "get_time"


def test_resolve_tools_mixed_inputs() -> None:
    resolved = resolve_tools(["grn:*:tool/get_time:*", "calculate"], org_id="acme")
    assert resolved == ["grn:acme:tool/get_time:1", "grn:acme:tool/calculate:1"]
