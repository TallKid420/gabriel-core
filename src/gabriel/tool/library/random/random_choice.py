"""random_choice — pick a random element from a list."""

from __future__ import annotations
from langchain_core.tools import tool

import random


@tool
async def random_choice(items: list) -> dict:
    """Pick a random element from a list.

    Args:
        items: A non-empty list of values.

    Returns:
        ``{"items", "choice"}`` on success or ``{"error": ...}`` if empty.
    """
    if not items:
        return {"error": "List is empty"}
    choice = random.choice(items)
    return {"items": items, "choice": choice}
