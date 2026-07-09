"""list_calendars — list all calendars accessible to the org's Google account."""
from __future__ import annotations
from typing import Any
from gabriel.tool.library.calendar._calendar_client import build_calendar_service


async def list_calendars(_credentials: dict[str, Any] | None = None) -> dict:
    """List all Google Calendars accessible to the org.

    Args:
        _credentials: Injected by executor — org-scoped Google Calendar credentials.

    Returns:
        ``{"calendars": [{"id", "summary", "primary", "access_role"}, ...], "count": N}``
        or ``{"error": ...}``.
    """
    if not _credentials:
        return {"error": "Google Calendar credentials not configured for this org."}
    try:
        service = build_calendar_service(_credentials)
        result = service.calendarList().list().execute()
        items = result.get("items", [])
        calendars = [
            {
                "id": item.get("id"),
                "summary": item.get("summary"),
                "primary": item.get("primary", False),
                "access_role": item.get("accessRole"),
            }
            for item in items
        ]
        return {"calendars": calendars, "count": len(calendars)}
    except Exception as exc:
        return {"error": str(exc)}
