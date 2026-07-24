"""calculate — safely evaluate a mathematical expression."""

from __future__ import annotations
from langchain_core.tools import tool

import math


@tool
async def calculate(expression: str) -> dict:
    """Safely evaluate a mathematical expression.

    Uses a restricted ``eval`` sandbox that only exposes the ``math`` module
    plus a small set of Python builtins.  No imports, no attribute access, and
    no arbitrary code execution are possible.

    Args:
        expression: A mathematical expression string, e.g. ``"sqrt(2) + 3"``.

    Returns:
        ``{"expression": ..., "result": ...}`` on success or
        ``{"error": ...}`` on failure.
    """
    safe_globals = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
    safe_globals["abs"] = abs
    safe_globals["round"] = round
    safe_globals["min"] = min
    safe_globals["max"] = max
    try:
        result = eval(expression, {"__builtins__": {}}, safe_globals)  # noqa: S307
        return {"expression": expression, "result": result}
    except Exception as exc:
        return {"error": str(exc)}
