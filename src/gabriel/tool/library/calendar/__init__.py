"""gabriel.tool.library.calendar
================================
Google Calendar integration tools.

All 9 callables are registered under the ``integration.google_calendar.*``
namespace in the platform FunctionRegistry.

Each tool accepts a ``_credentials`` dict injected by the executor.
The dict must contain Google OAuth2 token data as returned by
``ExternalIntegrationService.get_credentials()``.
"""

from __future__ import annotations

from gabriel.tool.registry import function_registry

from .list_calendars import list_calendars
from .list_events import list_events
from .get_event import get_event
from .create_event import create_event
from .update_event import update_event
from .delete_event import delete_event
from .find_free_slot import find_free_slot
from .accept_invitation import accept_invitation
from .decline_invitation import decline_invitation

# ---------------------------------------------------------------------------
# Register every callable under the integration.google_calendar.* namespace
# ---------------------------------------------------------------------------
_CALENDAR_TOOLS: dict[str, object] = {
    "integration.google_calendar.list_calendars": list_calendars,
    "integration.google_calendar.list_events": list_events,
    "integration.google_calendar.get_event": get_event,
    "integration.google_calendar.create_event": create_event,
    "integration.google_calendar.update_event": update_event,
    "integration.google_calendar.delete_event": delete_event,
    "integration.google_calendar.find_free_slot": find_free_slot,
    "integration.google_calendar.accept_invitation": accept_invitation,
    "integration.google_calendar.decline_invitation": decline_invitation,
}

function_registry.register_many(_CALENDAR_TOOLS)

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
