"""create_event — create a new Google Calendar event."""
from __future__ import annotations
from typing import Any
from gabriel.tool.library.calendar._calendar_client import build_calendar_service


async def create_event(
    summary: str,
    start: str,
    end: str,
    calendar_id: str = "primary",
    description: str = "",
    location: str = "",
    attendees: list[str] | None = None,
    _credentials: dict[str, Any] | None = None,
) -> dict:
    """Create a new event in Google Calendar.

    Args:
        summary:      Event title.
        start:        Start datetime in ISO-8601 format with timezone offset
                      (e.g. ``"2026-07-10T09:00:00-05:00"``).
        end:          End datetime in ISO-8601 format with timezone offset.
        calendar_id:  Calendar ID (default ``"primary"``).
        description:  Optional event description.
        location:     Optional event location.
        attendees:    Optional list of attendee email addresses.
        _credentials: Injected by executor — org-scoped Google Calendar credentials.

    Returns:
        ``{"id", "summary", "html_link", "status"}`` or ``{"error": ...}``.
    """
    if not _credentials:
        return {"error": "Google Calendar credentials not configured for this org."}
    try:
        service = build_calendar_service(_credentials)
        body: dict[str, Any] = {
            "summary": summary,
            "description": description,
            "location": location,
            "start": {"dateTime": start},
            "end": {"dateTime": end},
        }
        if attendees:
            body["attendees"] = [{"email": a} for a in attendees]

        event = service.events().insert(calendarId=calendar_id, body=body).execute()
        return {
            "id": event.get("id"),
            "summary": event.get("summary"),
            "html_link": event.get("htmlLink"),
            "status": event.get("status"),
        }
    except Exception as exc:
        return {"error": str(exc)}
