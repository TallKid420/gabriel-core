"""Runtime tool execution framework (Phase 3 — Gateway AI Runtime).

The Gateway executes tools *when the LLM requests them* mid-conversation.
This module provides:

* :class:`RuntimeTool` — base interface for runtime-invocable tools;
* :class:`FunctionTool` — wrap any async callable as a tool (also the adapter
  for callables already registered in the Phase-4
  :class:`~gabriel.tool.registry.FunctionRegistry`);
* :class:`RuntimeToolRegistry` — named lookup + LLM tool-spec export;
* :func:`build_default_tool_registry` — builds the registry from the
  dynamically discovered tool catalog (see
  :mod:`gabriel.tool.discovery`) instead of a hard-coded tool list;
* :func:`execute_tool_call` — run one model-requested call and normalise the
  result into a ``tool``-role message payload for the follow-up LLM turn.

Relationship to ``gabriel.tool`` (governed tool system)
-------------------------------------------------------
The Phase-4 ToolExecutor governs *resource-addressed* tools (GRN + PEEL +
JSON-Schema validation). The Gateway layer is intentionally lighter: it deals
in the small set of tools an agent's specification allows, formatted for the
LLM's function-calling API. ``FunctionTool.from_function_registry`` bridges
the two worlds so existing library callables are reusable without
re-implementation.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from gabriel.gateway.providers.base import ToolCallRequest
from gabriel.logging_config import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from langchain_core.tools import BaseTool

logger = get_logger(__name__)


class ToolExecutionError(Exception):
    """A runtime tool failed while executing."""


class UnknownToolError(ToolExecutionError):
    """The model requested a tool that is not registered/allowed."""


@dataclass(frozen=True)
class ToolResult:
    """Outcome of one tool call, ready to feed back to the LLM."""

    tool_call_id: str
    name: str
    content: str
    success: bool = True
    error: str | None = None

    def to_message_dict(self) -> dict[str, Any]:
        """Shape of the ``tool``-role message appended to the prompt."""
        return {
            "role": "tool",
            "name": self.name,
            "tool_call_id": self.tool_call_id,
            "content": self.content,
        }


class RuntimeTool(ABC):
    """Base interface for tools the Gateway runtime can execute."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name presented to the LLM (snake_case)."""

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description the LLM uses to decide when to call it."""

    @property
    def parameters(self) -> dict[str, Any]:
        """JSON Schema of accepted arguments (default: no arguments)."""
        return {"type": "object", "properties": {}, "required": []}

    @abstractmethod
    async def run(self, **kwargs: Any) -> dict[str, Any]:
        """Execute and return a JSON-serialisable result dict."""

    def to_llm_spec(self) -> dict[str, Any]:
        """OpenAI/Ollama-style function-calling tool specification."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class FunctionTool(RuntimeTool):
    """Adapt a plain async callable into a :class:`RuntimeTool`."""

    _name: str
    _description: str
    _fn: Callable[..., Awaitable[dict[str, Any]]]
    _parameters: dict[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}, "required": []}
    )

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        return await self._fn(**kwargs)

    @classmethod
    def from_function_registry(
        cls,
        binding: str,
        *,
        description: str,
        parameters: dict[str, Any] | None = None,
        name: str | None = None,
    ) -> "FunctionTool":
        """Bridge a Phase-4 FunctionRegistry binding (e.g. ``"math.calculate"``)
        into a runtime tool. The library package must already be imported so
        the binding is registered."""
        from gabriel.tool.registry import function_registry

        fn = function_registry.require(binding)
        return cls(
            _name=name or binding.replace(".", "_"),
            _description=description,
            _fn=fn,
            _parameters=parameters
            or {"type": "object", "properties": {}, "required": []},
        )


@dataclass
class LangChainTool(RuntimeTool):
    """Adapt a LangChain ``@tool``-decorated object into a :class:`RuntimeTool`.

    The agent invokes the tool directly through LangChain
    (``lc_tool.ainvoke(args)``) rather than through the OpenAI function-spec
    bridge. Governed metadata (safety level and GRN) rides alongside the tool
    so the runtime can gate ``REQUIRES_CONFIRMATION`` tools without deleting
    the governance layer.
    """

    lc_tool: "BaseTool"
    safety_level: int = 0
    tool_grn: str | None = None
    _parameters_override: dict[str, Any] | None = None

    @property
    def name(self) -> str:
        return self.lc_tool.name

    @property
    def description(self) -> str:
        return self.lc_tool.description or self.lc_tool.name

    @property
    def parameters(self) -> dict[str, Any]:
        if self._parameters_override is not None:
            return self._parameters_override
        from gabriel.tool.discovery import _lc_parameters

        return _lc_parameters(self.lc_tool)

    @property
    def requires_confirmation(self) -> bool:
        return self.safety_level == 1

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        result = await self.lc_tool.ainvoke(kwargs)
        if isinstance(result, dict):
            return result
        return {"result": result}


class RuntimeToolRegistry:
    """Named registry of runtime tools, exported to providers as LLM specs."""

    def __init__(self) -> None:
        self._tools: dict[str, RuntimeTool] = {}

    def register(self, tool: RuntimeTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Runtime tool already registered: '{tool.name}'")
        self._tools[tool.name] = tool

    def get(self, name: str) -> RuntimeTool:
        tool = self._tools.get(name)
        if tool is None:
            raise UnknownToolError(
                f"No runtime tool registered with name: '{name}'. "
                f"Available: {sorted(self._tools) or 'none'}"
            )
        return tool

    def is_registered(self, name: str) -> bool:
        return name in self._tools

    def list_tools(self) -> list[str]:
        return sorted(self._tools)

    def llm_specs(self, allowed: list[str] | None = None) -> list[dict[str, Any]]:
        """Tool specs for the provider payload.

        Args:
            allowed: Restrict to this subset (the agent's ``allowed_tools``);
                     ``None`` exports every registered tool.
        """
        names = self.list_tools() if allowed is None else [
            n for n in allowed if n in self._tools
        ]
        return [self._tools[n].to_llm_spec() for n in names]

    def __len__(self) -> int:
        return len(self._tools)


def build_default_tool_registry() -> RuntimeToolRegistry:
    """Registry pre-loaded from the dynamically discovered tool catalog.

    Uses :data:`gabriel.tool.discovery.tool_indexer` to walk
    ``gabriel.tool.library`` (and any third-party ``gabriel.tools`` entry
    points) instead of a hard-coded tool list, so newly added library tools
    are exposed automatically without touching this module.
    """
    from langchain_core.tools import BaseTool

    from gabriel.tool.discovery import tool_indexer

    registry = RuntimeToolRegistry()
    for discovered in tool_indexer.discover():
        fn = discovered.fn
        if isinstance(fn, BaseTool):
            # Register the LangChain tool object directly so the agent invokes
            # it via ``tool.invoke(...)`` / ``tool.ainvoke(...)``.
            registry.register(
                LangChainTool(
                    lc_tool=fn,
                    safety_level=int(discovered.safety_level),
                    tool_grn=str(discovered.grn),
                    _parameters_override=discovered.parameters,
                )
            )
        else:  # pragma: no cover - legacy/raw callables
            registry.register(
                FunctionTool(
                    _name=discovered.name,
                    _description=discovered.description,
                    _fn=fn,
                    _parameters=discovered.parameters,
                )
            )
    return registry


async def execute_tool_call(
    registry: RuntimeToolRegistry,
    call: ToolCallRequest,
    *,
    allowed: list[str] | None = None,
) -> ToolResult:
    """Execute one model-requested tool call, never raising.

    Failures come back as unsuccessful :class:`ToolResult` objects so the
    error text is fed to the LLM as a tool message (letting the model
    recover) instead of aborting the stream.
    """
    if allowed is not None and call.name not in allowed:
        error = f"Tool '{call.name}' is not allowed for this agent."
        return ToolResult(
            tool_call_id=call.id, name=call.name,
            content=json.dumps({"error": error}), success=False, error=error,
        )
    try:
        tool = registry.get(call.name)
        result = await tool.run(**call.arguments)
        return ToolResult(
            tool_call_id=call.id,
            name=call.name,
            content=json.dumps(result, default=str),
        )
    except Exception as exc:  # noqa: BLE001 — errors are surfaced to the LLM
        logger.exception("Runtime tool '%s' failed", call.name)
        error = str(exc)
        return ToolResult(
            tool_call_id=call.id,
            name=call.name,
            content=json.dumps({"error": error}),
            success=False,
            error=error,
        )
