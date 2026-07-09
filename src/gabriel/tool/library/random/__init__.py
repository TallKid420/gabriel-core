"""Random tool library — self-registers at import time."""

from gabriel.tool.library.random.generate_uuid import generate_uuid
from gabriel.tool.library.random.random_choice import random_choice
from gabriel.tool.library.random.random_number import random_number
from gabriel.tool.registry import function_registry

function_registry.register_many(
    {
        "random.generate_uuid": generate_uuid,
        "random.random_choice": random_choice,
        "random.random_number": random_number,
    }
)

__all__ = ["generate_uuid", "random_choice", "random_number"]
