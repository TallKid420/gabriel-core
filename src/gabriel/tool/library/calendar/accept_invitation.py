"""accept_invitation — accept a Google Calendar event invitation."""
from __future__ import annotations
from typing import Any
from gabriel.tool.library.calendar._calendar_client import build_calendar_service


async def accept_invitation(
    event_id: str,
    calendar_id: str = "primary",
    _credentials: dict[str, Any] | None = None,
) -> dict:
    """Accept a Google Calendar event invitation.

    Patches the authenticated user's attendee record to ``"accepted"``.

    Args:
        event_id:     The Google Calendar event ID.
        calendar_id:  Calendar ID (default ``"primary"``).
        _credentials: Injected by executor — org-scoped Google Calendar credentials.

    Returns:
        ``{"status": "accepted", "event_id": ...}`` or ``{"error": ...}``.
    """
    if not _credentials:
        return {"error": "Google Calendar credentials not configured for this org."}
    try:
        service = build_calendar_service(_credentials)
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()

        attendees = event.get("attendees", [])
        # Mark the org's email address as accepted
        user_email = _credentials.get("username") or _credentials.get("email", "")
        for attendee in attendees:
            if attendee.get("self") or (
                user_email and attendee.get("email", "").lower() == user_email.lower()
            ):
                attendee["responseStatus"] = "accepted"

        updated = (
            service.events()
            .patch(
                calendarId=calendar_id,
                eventId=event_id,
                body={"attendees": attendees},
            )
            .execute()
        )
        return {"status": "accepted", "event_id": updated.get("id")}
    except Exception as exc:
        return {"error": str(exc)}
