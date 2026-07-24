"""days_between — return the number of days between two ISO dates."""

from __future__ import annotations
from langchain_core.tools import tool

from datetime import date


@tool
async def days_between(date1: str, date2: str) -> dict:
    """Return the number of calendar days between two ISO-8601 dates.

    Args:
        date1: First date in ``YYYY-MM-DD`` format.
        date2: Second date in ``YYYY-MM-DD`` format.

    Returns:
        ``{"date1", "date2", "days"}`` on success or ``{"error": ...}``.
    """
    try:
        d1 = date.fromisoformat(date1)
        d2 = date.fromisoformat(date2)
        delta = abs((d2 - d1).days)
        return {"date1": date1, "date2": date2, "days": delta}
    except ValueError as exc:
        return {"error": str(exc)}
