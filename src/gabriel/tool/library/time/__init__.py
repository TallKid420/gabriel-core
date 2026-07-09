"""Time tool library — self-registers at import time."""

from gabriel.tool.library.time.days_between import days_between
from gabriel.tool.library.time.get_current_weather import get_current_weather
from gabriel.tool.library.time.get_time import get_time
from gabriel.tool.registry import function_registry

function_registry.register_many(
    {
        "time.days_between": days_between,
        "time.get_current_weather": get_current_weather,
        "time.get_time": get_time,
    }
)

__all__ = ["days_between", "get_current_weather", "get_time"]
