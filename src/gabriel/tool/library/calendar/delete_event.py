"""delete_event — permanently delete a Google Calendar event."""
from __future__ import annotations
from typing import Any
from gabriel.tool.library.calendar._calendar_client import build_calendar_service


async def delete_event(
    event_id: str,
    calendar_id: str = "primary",
    _credentials: dict[str, Any] | None = None,
) -> dict:
    """Delete a Google Calendar event.

    Args:
        event_id:     The Google Calendar event ID to delete.
        calendar_id:  Calendar ID (default ``"primary"``).
        _credentials: Injected by executor — org-scoped Google Calendar credentials.

    Returns:
        ``{"status": "deleted", "event_id": ...}`` or ``{"error": ...}``.
    """
    if not _credentials:
        return {"error": "Google Calendar credentials not configured for this org."}
    try:
        service = build_calendar_service(_credentials)
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return {"status": "deleted", "event_id": event_id}
    except Exception as exc:
        return {"error": str(exc)}
