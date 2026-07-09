"""get_time — return the current time in a given timezone."""

from __future__ import annotations

from datetime import datetime


async def get_time(timezone: str = "UTC") -> dict:
    """Return the current ISO-8601 timestamp in the requested timezone.

    Args:
        timezone: IANA timezone name, e.g. ``"America/New_York"``, ``"UTC"``.
                  Defaults to ``"UTC"``.

    Returns:
        ``{"timezone", "time"}`` on success or ``{"error": ...}``.
    """
    try:
        import pytz  # type: ignore[import]

        tz = pytz.timezone(timezone)
        time_str = datetime.now(tz).isoformat(timespec="seconds")
        return {"timezone": timezone, "time": time_str}
    except ImportError:
        return {"error": "pytz is not installed"}
    except Exception as exc:  # pytz.UnknownTimeZoneError is a subclass of Exception
        return {"error": f"Unknown timezone: {timezone} ({exc})"}
