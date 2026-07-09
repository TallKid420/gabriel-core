"""get_current_weather — fetch current weather via the free wttr.in JSON API."""

from __future__ import annotations

import json
from urllib import error, parse, request


async def get_current_weather(location: str, unit: str = "f") -> dict:
    """Get current weather for a location using the wttr.in JSON API.

    No API key is required.  wttr.in is a public weather service.

    Args:
        location: City name, coordinates, or airport code (e.g. ``"London"``).
        unit:     Temperature unit — ``"f"`` (Fahrenheit, default) or ``"c"`` (Celsius).

    Returns:
        A dict with location info, temperature, condition, humidity, and wind
        data on success, or ``{"error": ...}`` on failure.
    """
    loc = str(location).strip()
    if not loc:
        return {"error": "location is required"}

    unit_l = str(unit or "f").strip().lower()
    if unit_l not in {"c", "f"}:
        return {"error": "unit must be 'c' or 'f'"}

    try:
        encoded = parse.quote(loc)
        url = f"https://wttr.in/{encoded}?format=j1"
        req = request.Request(
            url=url, method="GET", headers={"User-Agent": "Gabriel/2.0"}
        )
        with request.urlopen(req, timeout=20) as resp:  # noqa: S310
            raw = resp.read(250_000).decode("utf-8", errors="replace")
            data = json.loads(raw)

        current = (data.get("current_condition") or [{}])[0]
        area = (data.get("nearest_area") or [{}])[0]
        area_name = ((area.get("areaName") or [{"value": loc}])[0]).get("value", loc)
        region_name = ((area.get("region") or [{"value": ""}])[0]).get("value", "")
        country_name = ((area.get("country") or [{"value": ""}])[0]).get("value", "")

        if unit_l == "c":
            temperature = current.get("temp_C")
            feels_like = current.get("FeelsLikeC")
            temp_unit = "C"
        else:
            temperature = current.get("temp_F")
            feels_like = current.get("FeelsLikeF")
            temp_unit = "F"

        return {
            "location": {
                "query": loc,
                "area": area_name,
                "region": region_name,
                "country": country_name,
            },
            "temperature": temperature,
            "feels_like": feels_like,
            "temperature_unit": temp_unit,
            "condition": (
                (current.get("weatherDesc") or [{"value": ""}])[0]
            ).get("value", ""),
            "humidity": current.get("humidity"),
            "wind_kph": current.get("windspeedKmph"),
            "wind_mph": current.get("windspeedMiles"),
            "observation_time_utc": current.get("observation_time"),
            "source": "wttr.in",
        }
    except error.HTTPError as exc:
        return {"error": f"Weather request failed with HTTP {exc.code}"}
    except Exception as exc:
        return {"error": f"Weather lookup failed: {exc}"}
