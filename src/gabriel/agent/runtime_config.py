"""
NOTE: LangGraph, DSPy, OpenAI, CrewAI will all consume this.
"""

class RuntimeConfiguration:
    runtime: str
    timeout_seconds: int
    max_iterations: int
    temperature: float
    max_tokens: int