"""random_number — generate a random float in a range."""

from __future__ import annotations

import random


async def random_number(min_value: float = 0, max_value: float = 100) -> dict:
    """Generate a random float between min_value and max_value.

    Args:
        min_value: Lower bound (inclusive, default 0).
        max_value: Upper bound (inclusive, default 100).

    Returns:
        ``{"min", "max", "result"}`` on success or ``{"error": ...}``.
    """
    if min_value > max_value:
        return {"error": "min_value must be ≤ max_value"}
    result = random.uniform(min_value, max_value)
    return {"min": min_value, "max": max_value, "result": round(result, 6)}
