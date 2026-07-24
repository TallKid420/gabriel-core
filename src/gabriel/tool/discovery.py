"""ToolLibraryIndexer — dynamic tool discovery (ADR-016).

Gabriel Core used to hard-code its tool catalog: every package under
``gabriel.tool.library`` called ``function_registry.register_many(...)`` by
hand, and the Gateway's runtime tool registry only ever knew about one
built-in tool. This module replaces that manual bookkeeping with discovery:

* Every module inside ``gabriel.tool.library`` whose public async function
  shares the module's name is treated as a tool implementation. Its LLM
  schema (name, description, parameters) is derived purely from the
  function's signature, type hints and docstring — no separate metadata
  file to keep in sync.
* Third parties may contribute additional tools without touching this
  repository at all, via a ``gabriel.tools`` entry point group.

The indexer is the single source of truth consumed by:

* :func:`gabriel.gateway.tools.build_default_tool_registry` (LLM-facing
  runtime tools);
* :mod:`scripts.seed_tools` (syncing ``Tool`` governance resources);
* :class:`gabriel.tool.executor.ToolExecutor` (via the shared
  :class:`~gabriel.tool.registry.FunctionRegistry`).
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from importlib.metadata import entry_points
from typing import Any, Awaitable, Callable

from langchain_core.tools import BaseTool

from gabriel.logging_config import get_logger
from gabriel.resource.grn import GRN
from gabriel.tool.registry import FunctionRegistry
from gabriel.tool.models import Tool, ToolCategory, SafetyLevel, ExecutionRuntime

logger = get_logger(__name__)

LIBRARY_PACKAGE = "gabriel.tool.library"
ENTRY_POINT_GROUP = "gabriel.tools"

_JSON_TYPE_BY_ANNOTATION: dict[Any, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    dict: "object",
    list: "array",
}

_CATEGORY_VALUES = {c.value for c in ToolCategory}


def _json_type_for(annotation: Any) -> str:
    """Best-effort JSON Schema type for a Python type annotation."""
    return _JSON_TYPE_BY_ANNOTATION.get(annotation, "string")


def _short_description(fn: Callable[..., Any]) -> str:
    """First paragraph of the function's docstring, collapsed to one line."""
    doc = inspect.getdoc(fn) or ""
    first_paragraph = doc.strip().split("\n\n", 1)[0]
    return " ".join(first_paragraph.split())


def _parameters_schema(fn: Callable[..., Any]) -> dict[str, Any]:
    """Derive a JSON Schema for *fn*'s LLM-facing parameters.

    Parameters whose name starts with ``_`` are executor-injected metadata
    (e.g. ``_org_id``, ``_credentials``) and are never exposed to the LLM.
    """
    signature = inspect.signature(fn)
    try:
        import typing

        hints = typing.get_type_hints(fn)
    except Exception:  # noqa: BLE001 - best-effort; fall back to raw annotations
        hints = {}

    properties: dict[str, Any] = {}
    required: list[str] = []
    for param_name, param in signature.parameters.items():
        if param_name.startswith("_"):
            continue
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        annotation = hints.get(param_name, param.annotation)
        properties[param_name] = {"type": _json_type_for(annotation)}
        if param.default is inspect.Parameter.empty:
            required.append(param_name)
    return {"type": "object", "properties": properties, "required": required}


def _lc_parameters(lc_tool: BaseTool) -> dict[str, Any]:
    """Derive an OpenAI-style JSON Schema from a LangChain tool's args schema.

    Underscore-prefixed / executor-injected arguments are already excluded by
    the ``@tool`` decorator, so the schema only ever exposes LLM-facing args.
    """
    args_schema = getattr(lc_tool, "args_schema", None)
    if args_schema is None:
        return {"type": "object", "properties": {}, "required": []}
    try:
        schema = args_schema.model_json_schema()  # pydantic v2
    except AttributeError:  # pragma: no cover - defensive
        return {"type": "object", "properties": {}, "required": []}
    return {
        "type": "object",
        "properties": schema.get("properties", {}),
        "required": schema.get("required", []),
    }


def lc_tool_to_async_callable(
    lc_tool: BaseTool,
) -> Callable[..., Awaitable[dict[str, Any]]]:
    """Adapt a LangChain tool into the ``async fn(**kwargs) -> dict`` shape the
    :class:`~gabriel.tool.executor.ToolExecutor` and
    :class:`~gabriel.tool.registry.FunctionRegistry` expect.

    The adapter invokes the tool through LangChain (``ainvoke``) so all runtime
    dispatch flows through the LangChain tool object rather than the raw
    callable.
    """

    async def _invoke(**kwargs: Any) -> dict[str, Any]:
        result = await lc_tool.ainvoke(kwargs)
        if isinstance(result, dict):
            return result
        return {"result": result}

    _invoke.__name__ = getattr(lc_tool, "name", "lc_tool")
    return _invoke


class ToolLibraryIndexer:
    """Discovers tool implementations from the library package and entry points."""

    def __init__(self) -> None:
        self._cache: list[Tool] | None = None

    def discover(self, *, force: bool = False) -> list[Tool]:
        """Return every discovered tool, caching the result.

        Args:
            force: Re-scan even if a cached result exists.
        """
        if self._cache is not None and not force:
            return self._cache

        tools: dict[str, Tool] = {}
        self._discover_library(tools)
        self._discover_entry_points(tools)
        self._cache = list(tools.values())
        return self._cache

    def register_into(
        self, fn_registry: FunctionRegistry, *, force: bool = False
    ) -> None:
        """Register every discovered tool's callable into *fn_registry*."""
        for tool in self.discover(force=force):
            if tool.fn is None:
                continue
            if fn_registry.is_registered(tool.runtime_binding):
                continue
            # ``tool.fn`` is a LangChain tool object; register an async adapter
            # so the ToolExecutor can dispatch it via ``await fn(**kwargs)``
            # (which invokes the tool through LangChain under the hood).
            callable_fn = (
                lc_tool_to_async_callable(tool.fn)
                if isinstance(tool.fn, BaseTool)
                else tool.fn
            )
            fn_registry.register(binding=tool.runtime_binding, fn=callable_fn)

    # ------------------------------------------------------------------
    # Discovery sources
    # ------------------------------------------------------------------

    def _discover_library(self, tools: dict[str, Tool]) -> None:
        library = importlib.import_module(LIBRARY_PACKAGE)

        for pkg_info in pkgutil.iter_modules(library.__path__, prefix=f"{LIBRARY_PACKAGE}."):
            namespace = pkg_info.name.rsplit(".", 1)[-1]
            if not pkg_info.ispkg or namespace.startswith("_"):
                continue

            library_pkg = importlib.import_module(pkg_info.name)
            
            for mod_info in pkgutil.iter_modules(library_pkg.__path__, prefix=f"{library_pkg.__name__}."):
                tool_name = mod_info.name.rsplit(".", 1)[-1]

                if mod_info.ispkg or tool_name.startswith("_"):
                    continue

                logger.debug(f"Discovered module: {mod_info.name} under category: {namespace}")

                try:
                    module = importlib.import_module(mod_info.name)
                except ImportError:
                    logger.warning(f"Skipping tool module {mod_info.name} (import failed)", exc_info=True)
                    continue
                    
                # Clean values for tool input
                org_id = ""  # FIXME: Determine how to get the org_id
                category = ToolCategory(namespace) if namespace in _CATEGORY_VALUES else ToolCategory.CUSTOM
                binding = f"{namespace}.{tool_name}"
                grn = GRN(org_id=org_id, resource_id=tool_name, resource_type="tool")

                fn = getattr(module, tool_name, None)
                # Tools are LangChain ``@tool``-decorated objects (BaseTool).
                if not isinstance(fn, BaseTool):
                    continue

                tools[tool_name] = Tool(
                    grn=grn,  # GRN is assigned later when syncing to governance
                    org_id="",  # Org ID is assigned later when syncing to governance
                    name=tool_name,
                    description=fn.description or _short_description(fn),
                    category=category,
                    parameters=_lc_parameters(fn),
                    safety_level=SafetyLevel.SAFE,  # Default safety level; can be updated later
                    runtime_binding=binding,
                    execution_runtime=ExecutionRuntime.LOCAL,
                    fn=fn,
                    created_by="system",
                    updated_by="system",
                )

    def _discover_entry_points(self, tools: dict[str, Tool]) -> None:
        try:
            eps = entry_points(group=ENTRY_POINT_GROUP)
        except TypeError:  # pragma: no cover - Python < 3.10 selectable API
            eps_all = entry_points()
            if hasattr(eps_all, "select"):
                eps = eps_all.select(group=ENTRY_POINT_GROUP)
            elif isinstance(eps_all, dict):
                eps = eps_all.get(ENTRY_POINT_GROUP, [])
            else:
                eps = [ep for ep in eps_all if getattr(ep, "group", "") == ENTRY_POINT_GROUP]

        for ep in eps:
            try:
                fn = ep.load()
            except Exception:  # noqa: BLE001 - a broken plugin must not break discovery
                logger.warning(
                    "Failed to load tool entry point '%s'", ep.name, exc_info=True
                )
                continue
            # Accept either a LangChain tool object or a bare async callable
            # (wrapped into a LangChain tool for a uniform runtime contract).
            if not isinstance(fn, BaseTool):
                if inspect.iscoroutinefunction(fn):
                    from langchain_core.tools import tool as _lc_tool

                    fn = _lc_tool(fn)
                else:
                    logger.warning(
                        "Entry point '%s' does not resolve to a LangChain tool "
                        "or async callable; skipping",
                        ep.name,
                    )
                    continue

            category = ToolCategory.CUSTOM
            binding = ep.name

            tools[ep.name] = Tool(
                grn=GRN(org_id="", resource_id=ep.name, resource_type="tool"),
                org_id="",  # Org ID is assigned later when syncing to governance
                name=ep.name,
                description=fn.description or _short_description(fn),
                category=category,
                parameters=_lc_parameters(fn),
                safety_level=SafetyLevel.SAFE,  # Default safety level; can be updated later
                runtime_binding=binding,
                execution_runtime=ExecutionRuntime.LOCAL,
                fn=fn,
                created_by="system",
                updated_by="system",
            )



tool_indexer = ToolLibraryIndexer()
