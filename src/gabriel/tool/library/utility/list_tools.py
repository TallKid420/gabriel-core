"""list_tools — enumerate registered tool bindings from the FunctionRegistry."""

from __future__ import annotations
from langchain_core.tools import tool


@tool
async def list_tools() -> dict:
    """List all currently registered tool runtime bindings.

    This introspects the in-process :class:`~gabriel.tool.registry.FunctionRegistry`
    and returns a sorted list of binding keys.  It does NOT query the database —
    it reflects what is importable and registered in this process.

    Returns:
        ``{"tools": ["math.calculate", ...], "count": N}``.
    """
    from gabriel.tool.registry import function_registry

    bindings = function_registry.list_bindings()
    return {"tools": bindings, "count": len(bindings)}
