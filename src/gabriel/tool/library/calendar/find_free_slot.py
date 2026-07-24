"""find_free_slot — find the next free time slot in Google Calendar."""
from __future__ import annotations
from langchain_core.tools import tool
from datetime import datetime, timedelta, timezone
from typing import Any
from gabriel.tool.library.calendar._calendar_client import build_calendar_service


@tool
async def find_free_slot(
    duration_minutes: int = 60,
    calendar_id: str = "primary",
    search_days: int = 7,
    _credentials: dict[str, Any] | None = None,
) -> dict:
    """Find the next available free slot of a given duration.

    Uses the Google Calendar FreeBusy API to query busy periods and returns
    the first gap that accommodates the requested duration within working hours
    (09:00–17:00 local time, Monday–Friday).

    Args:
        duration_minutes: Required slot length in minutes (default 60).
        calendar_id:      Calendar ID to check (default ``"primary"``).
        search_days:      How many days ahead to search (default 7).
        _credentials:     Injected by executor — org-scoped Google Calendar credentials.

    Returns:
        ``{"start", "end", "duration_minutes"}`` or ``{"error": ...}``.
    """
    if not _credentials:
        return {"error": "Google Calendar credentials not configured for this org."}
    try:
        service = build_calendar_service(_credentials)
        now = datetime.now(timezone.utc)
        time_max = now + timedelta(days=search_days)

        body = {
            "timeMin": now.isoformat(),
            "timeMax": time_max.isoformat(),
            "items": [{"id": calendar_id}],
        }
        freebusy = service.freebusy().query(body=body).execute()
        busy_periods = freebusy.get("calendars", {}).get(calendar_id, {}).get("busy", [])

        # Normalise busy periods to datetime objects
        busy: list[tuple[datetime, datetime]] = []
        for period in busy_periods:
            s = datetime.fromisoformat(period["start"].replace("Z", "+00:00"))
            e = datetime.fromisoformat(period["end"].replace("Z", "+00:00"))
            busy.append((s, e))

        duration = timedelta(minutes=duration_minutes)
        candidate = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if candidate < now:
            candidate += timedelta(days=1)

        for _ in range(search_days * 24):  # hourly sweep
            # Skip weekends
            if candidate.weekday() >= 5:
                candidate = (candidate + timedelta(days=1)).replace(
                    hour=9, minute=0, second=0, microsecond=0
                )
                continue
            # Stay within working hours
            end_candidate = candidate + duration
            if end_candidate.hour > 17 or (end_candidate.hour == 17 and end_candidate.minute > 0):
                candidate = (candidate + timedelta(days=1)).replace(
                    hour=9, minute=0, second=0, microsecond=0
                )
                continue
            # Check for conflicts
            conflict = any(
                not (end_candidate <= b_start or candidate >= b_end)
                for b_start, b_end in busy
            )
            if not conflict:
                return {
                    "start": candidate.isoformat(),
                    "end": end_candidate.isoformat(),
                    "duration_minutes": duration_minutes,
                }
            candidate += timedelta(minutes=30)

        return {"error": f"No free slot found in the next {search_days} days."}
    except Exception as exc:
        return {"error": str(exc)}
