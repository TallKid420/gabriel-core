"""list_events — list upcoming calendar events."""
from __future__ import annotations
from langchain_core.tools import tool
from datetime import datetime, timezone
from typing import Any
from gabriel.tool.library.calendar._calendar_client import build_calendar_service


@tool
async def list_events(
    calendar_id: str = "primary",
    max_results: int = 10,
    time_min: str | None = None,
    _credentials: dict[str, Any] | None = None,
) -> dict:
    """List upcoming events from a Google Calendar.

    Args:
        calendar_id:  Calendar ID (default ``"primary"``).
        max_results:  Maximum number of events to return (default 10, max 250).
        time_min:     ISO-8601 datetime lower bound (default: now).
        _credentials: Injected by executor — org-scoped Google Calendar credentials.

    Returns:
        ``{"events": [...], "count": N}`` or ``{"error": ...}``.
    """
    if not _credentials:
        return {"error": "Google Calendar credentials not configured for this org."}
    try:
        service = build_calendar_service(_credentials)
        if time_min is None:
            time_min = datetime.now(timezone.utc).isoformat()
        result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                maxResults=min(max_results, 250),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = [
            {
                "id": e.get("id"),
                "summary": e.get("summary"),
                "start": e.get("start", {}).get("dateTime") or e.get("start", {}).get("date"),
                "end": e.get("end", {}).get("dateTime") or e.get("end", {}).get("date"),
                "location": e.get("location"),
                "status": e.get("status"),
            }
            for e in result.get("items", [])
        ]
        return {"events": events, "count": len(events)}
    except Exception as exc:
        return {"error": str(exc)}
