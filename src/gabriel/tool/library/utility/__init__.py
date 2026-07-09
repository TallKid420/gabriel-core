"""Utility tool library — self-registers at import time."""

from gabriel.tool.library.utility.ask_question import ask_question
from gabriel.tool.library.utility.list_tools import list_tools
from gabriel.tool.registry import function_registry

function_registry.register_many(
    {
        "utility.ask_question": ask_question,
        "utility.list_tools": list_tools,
    }
)

__all__ = ["ask_question", "list_tools"]
