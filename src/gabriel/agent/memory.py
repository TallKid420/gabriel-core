"""
NOTE: Agents delcare what memory they need.
"""

class MemoryRequirments:
    read_layers: list[str]
    write_layers: list[str]
    retention: str