"""Org-scoped Google Calendar API client.

Credentials are obtained from the org's ``GOOGLE_CALENDAR`` ExternalIntegration
record.  The expected credentials dict is a standard Google OAuth2 token JSON
as returned by ``google-auth-oauthlib``, with at minimum:

    {
        "token":         "<access_token>",
        "refresh_token": "<refresh_token>",
        "client_id":     "<client_id>",
        "client_secret": "<client_secret>",
        "token_uri":     "https://oauth2.googleapis.com/token",
        "scopes":        ["https://www.googleapis.com/auth/calendar"]
    }

The client uses ``google-api-python-client`` and ``google-auth`` which must be
installed:

    pip install google-api-python-client google-auth google-auth-oauthlib
"""

from __future__ import annotations

from typing import Any


def build_calendar_service(credentials: dict[str, Any]):
    """Build and return a Google Calendar API service object.

    Args:
        credentials: OAuth2 credentials dict (see module docstring).

    Returns:
        A Google API Resource object for the Calendar v3 API.

    Raises:
        ImportError: If google-api-python-client is not installed.
        google.auth.exceptions.TransportError: On network failures.
    """
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise ImportError(
            "google-api-python-client and google-auth are required for calendar tools. "
            "Install them with: pip install google-api-python-client google-auth"
        ) from exc

    creds = Credentials(
        token=credentials.get("token"),
        refresh_token=credentials.get("refresh_token"),
        client_id=credentials.get("client_id"),
        client_secret=credentials.get("client_secret"),
        token_uri=credentials.get("token_uri", "https://oauth2.googleapis.com/token"),
        scopes=credentials.get("scopes"),
    )
    return build("calendar", "v3", credentials=creds, cache_discovery=False)
