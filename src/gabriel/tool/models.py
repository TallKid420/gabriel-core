"""
tool/models.py
"""

from gabriel.resource.models import Resource

from typing import Any

class Tool(Resource):
    """A tool resource that defines a tool's metadata and capabilities.

    Tools are used to define the capabilities of agents and other entities in the system.
    """

    name: str
    """The name of the tool."""

    description: str
    """A brief description of the tool."""

    category: str
    """The category of the tool (e.g., "data_processing", "image_analysis")."""

    input_schema: dict[str, Any]
    """The JSON schema defining the expected input for the tool."""

    output_schema: dict[str, Any]
    """The JSON schema defining the expected output for the tool."""

    safety_level: int
    """An integer representing the safety level of the tool (e.g., 1-5)."""

    required_capabilities: list[str]
    """A list of capabilities required to use this tool."""