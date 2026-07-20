"""gabriel.tool.library.calendar
================================
Google Calendar integration tools.

All 9 callables are discovered under the ``integration.google_calendar.*``
namespace by :class:`gabriel.tool.discovery.ToolLibraryIndexer`.

Each tool accepts a ``_credentials`` dict injected by the executor.
The dict must contain Google OAuth2 token data as returned by
``ExternalIntegrationService.get_credentials()``.
"""

from __future__ import annotations

from .accept_invitation import accept_invitation
from .create_event import create_event
from .decline_invitation import decline_invitation
from .delete_event import delete_event
from .find_free_slot import find_free_slot
from .get_event import get_event
from .list_calendars import list_calendars
from .list_events import list_events
from .update_event import update_event

TOOL_NAMESPACE = "integration.google_calendar"

__all__ = [
    "list_calendars",
    "list_events",
    "get_event",
    "create_event",
    "update_event",
    "delete_event",
    "find_free_slot",
    "accept_invitation",
    "decline_invitation",
]
