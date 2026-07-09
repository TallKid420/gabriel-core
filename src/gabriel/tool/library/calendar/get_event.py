"""get_event — retrieve a single calendar event by ID."""
from __future__ import annotations
from typing import Any
from gabriel.tool.library.calendar._calendar_client import build_calendar_service


async def get_event(
    event_id: str,
    calendar_id: str = "primary",
    _credentials: dict[str, Any] | None = None,
) -> dict:
    """Retrieve details of a single Google Calendar event.

    Args:
        event_id:     The Google Calendar event ID.
        calendar_id:  Calendar ID (default ``"primary"``).
        _credentials: Injected by executor — org-scoped Google Calendar credentials.

    Returns:
        Event details dict or ``{"error": ...}``.
    """
    if not _credentials:
        return {"error": "Google Calendar credentials not configured for this org."}
    try:
        service = build_calendar_service(_credentials)
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        return {
            "id": event.get("id"),
            "summary": event.get("summary"),
            "description": event.get("description"),
            "location": event.get("location"),
            "start": event.get("start", {}).get("dateTime") or event.get("start", {}).get("date"),
            "end": event.get("end", {}).get("dateTime") or event.get("end", {}).get("date"),
            "attendees": [a.get("email") for a in event.get("attendees", [])],
            "status": event.get("status"),
            "html_link": event.get("htmlLink"),
        }
    except Exception as exc:
        return {"error": str(exc)}
