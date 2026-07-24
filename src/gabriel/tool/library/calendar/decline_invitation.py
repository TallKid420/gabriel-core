"""decline_invitation — Decline a Google Calendar event invitation.

runtime_binding: integration.google_calendar.decline_invitation
safety_level:    REQUIRES_CONFIRMATION
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "event_id": {
            "type": "string",
            "description": "The Google Calendar event ID to decline.",
        },
        "calendar_id": {
            "type": "string",
            "description": "Calendar ID. Defaults to 'primary'.",
            "default": "primary",
        },
        "comment": {
            "type": "string",
            "description": "Optional comment to send with the decline.",
            "default": "",
        },
        "_credentials": {
            "type": "object",
            "description": "Google OAuth2 credentials dict (injected by executor).",
        },
    },
    "required": ["event_id"],
}

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean"},
        "event_id": {"type": "string"},
        "status": {"type": "string"},
        "message": {"type": "string"},
    },
    "required": ["success"],
}


@tool
def decline_invitation(
    event_id: str,
    calendar_id: str = "primary",
    comment: str = "",
    _credentials: dict | None = None,
) -> dict[str, Any]:
    """Decline a Google Calendar event invitation.

    Sets the attendee response status to 'declined' for the authenticated user.

    Args:
        event_id:     The event ID to decline.
        calendar_id:  Calendar containing the event (default 'primary').
        comment:      Optional comment sent with the decline.
        _credentials: Google OAuth2 credentials dict (injected by executor).

    Returns:
        dict with keys: success (bool), event_id, status, message.
    """
    if not _credentials:
        return {
            "success": False,
            "event_id": event_id,
            "status": "error",
            "message": (
                "No Google credentials provided. "
                "Connect a Google account via ExternalIntegration to use calendar tools."
            ),
        }

    try:
        from gabriel.tool.library.calendar._calendar_client import build_calendar_service

        service = build_calendar_service(_credentials)

        # Fetch the current event to find the attendee entry for this user.
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()

        # Determine the authenticated user's email from credentials.
        user_email: str = _credentials.get("email", "").lower()

        attendees: list[dict] = event.get("attendees", [])
        updated = False
        for attendee in attendees:
            if not user_email or attendee.get("email", "").lower() == user_email:
                attendee["responseStatus"] = "declined"
                if comment:
                    attendee["comment"] = comment
                updated = True
                break

        if not updated:
            # No matching attendee found — patch self as declined anyway.
            patch_body: dict[str, Any] = {
                "attendees": attendees
                + [
                    {
                        "email": user_email or "me",
                        "responseStatus": "declined",
                        **({"comment": comment} if comment else {}),
                    }
                ]
            }
        else:
            patch_body = {"attendees": attendees}

        result = (
            service.events()
            .patch(
                calendarId=calendar_id,
                eventId=event_id,
                body=patch_body,
                sendUpdates="all",
            )
            .execute()
        )

        return {
            "success": True,
            "event_id": result.get("id", event_id),
            "status": "declined",
            "message": f"Successfully declined event '{result.get('summary', event_id)}'.",
        }

    except ImportError:
        return {
            "success": False,
            "event_id": event_id,
            "status": "error",
            "message": (
                "google-api-python-client is not installed. "
                "Run: pip install google-api-python-client google-auth"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "event_id": event_id,
            "status": "error",
            "message": str(exc),
        }
