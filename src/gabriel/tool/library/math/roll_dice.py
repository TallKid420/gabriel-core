"""roll_dice — roll one or more dice."""

from __future__ import annotations
from langchain_core.tools import tool

import random


@tool
async def roll_dice(sides: int = 6, count: int = 1) -> dict:
    """Roll one or more dice with a given number of sides.

    Args:
        sides: Number of faces on each die (minimum 2, default 6).
        count: Number of dice to roll (1–100, default 1).

    Returns:
        ``{"sides", "count", "rolls", "total"}``.
    """
    sides = max(2, int(sides))
    count = min(max(1, int(count)), 100)
    rolls = [random.randint(1, sides) for _ in range(count)]
    return {"sides": sides, "count": count, "rolls": rolls, "total": sum(rolls)}
