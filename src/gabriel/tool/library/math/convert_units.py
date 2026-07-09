"""convert_units — convert between common units of measurement."""

from __future__ import annotations


async def convert_units(value: float, from_unit: str, to_unit: str) -> dict:
    """Convert between common units of temperature, length, weight, and speed.

    Args:
        value:     Numeric value to convert.
        from_unit: Source unit (case-insensitive), e.g. ``"kg"``, ``"C"``.
        to_unit:   Target unit (case-insensitive), e.g. ``"lb"``, ``"F"``.

    Returns:
        ``{"value", "from", "to", "result"}`` on success or ``{"error": ...}``.
    """
    f, t = from_unit.lower(), to_unit.lower()

    conversions = {
        # Length (base: metres)
        "mm": 0.001, "cm": 0.01, "m": 1.0, "km": 1000.0,
        "in": 0.0254, "ft": 0.3048, "yd": 0.9144, "mi": 1609.344,
        # Mass (base: kilograms)
        "mg": 1e-6, "g": 0.001, "kg": 1.0, "lb": 0.453592, "oz": 0.028350, "t": 1000.0,
        # Speed (base: m/s)
        "mph": 0.44704, "kph": 0.27778, "m/s": 1.0, "knot": 0.51444,
    }

    temp_units = {"c", "f", "k"}
    if f in temp_units or t in temp_units:
        try:
            if f == "c" and t == "f":
                result = value * 9 / 5 + 32
            elif f == "f" and t == "c":
                result = (value - 32) * 5 / 9
            elif f == "c" and t == "k":
                result = value + 273.15
            elif f == "k" and t == "c":
                result = value - 273.15
            elif f == "f" and t == "k":
                result = (value - 32) * 5 / 9 + 273.15
            elif f == "k" and t == "f":
                result = (value - 273.15) * 9 / 5 + 32
            elif f == t:
                result = value
            else:
                return {"error": f"Unsupported temperature conversion: {f} → {t}"}
            return {
                "value": value,
                "from": from_unit,
                "to": to_unit,
                "result": round(result, 6),
            }
        except Exception as exc:
            return {"error": str(exc)}

    if f not in conversions or t not in conversions:
        return {"error": f"Unknown unit(s): '{from_unit}', '{to_unit}'"}

    base = value * conversions[f]
    result = base / conversions[t]
    return {"value": value, "from": from_unit, "to": to_unit, "result": round(result, 6)}
