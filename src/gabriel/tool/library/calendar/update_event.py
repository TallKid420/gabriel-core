"""update_event — update fields of an existing Google Calendar event."""
from __future__ import annotations
from langchain_core.tools import tool
from typing import Any
from gabriel.tool.library.calendar._calendar_client import build_calendar_service


@tool
async def update_event(
    event_id: str,
    calendar_id: str = "primary",
    summary: str | None = None,
    start: str | None = None,
    end: str | None = None,
    description: str | None = None,
    location: str | None = None,
    _credentials: dict[str, Any] | None = None,
) -> dict:
    """Update an existing Google Calendar event (patch semantics — only provided fields are changed).

    Args:
        event_id:     The Google Calendar event ID.
        calendar_id:  Calendar ID (default ``"primary"``).
        summary:      New title (optional).
        start:        New start datetime ISO-8601 (optional).
        end:          New end datetime ISO-8601 (optional).
        description:  New description (optional).
        location:     New location (optional).
        _credentials: Injected by executor — org-scoped Google Calendar credentials.

    Returns:
        Updated event summary dict or ``{"error": ...}``.
    """
    if not _credentials:
        return {"error": "Google Calendar credentials not configured for this org."}
    try:
        service = build_calendar_service(_credentials)
        patch: dict[str, Any] = {}
        if summary is not None:
            patch["summary"] = summary
        if description is not None:
            patch["description"] = description
        if location is not None:
            patch["location"] = location
        if start is not None:
            patch["start"] = {"dateTime": start}
        if end is not None:
            patch["end"] = {"dateTime": end}

        event = (
            service.events()
            .patch(calendarId=calendar_id, eventId=event_id, body=patch)
            .execute()
        )
        return {
            "id": event.get("id"),
            "summary": event.get("summary"),
            "status": event.get("status"),
            "html_link": event.get("htmlLink"),
        }
    except Exception as exc:
        return {"error": str(exc)}
