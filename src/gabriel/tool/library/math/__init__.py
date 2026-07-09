"""Math tool library — self-registers at import time."""

from gabriel.tool.library.math.calculate import calculate
from gabriel.tool.library.math.convert_units import convert_units
from gabriel.tool.library.math.roll_dice import roll_dice
from gabriel.tool.registry import function_registry

function_registry.register_many(
    {
        "math.calculate": calculate,
        "math.convert_units": convert_units,
        "math.roll_dice": roll_dice,
    }
)

__all__ = ["calculate", "convert_units", "roll_dice"]
