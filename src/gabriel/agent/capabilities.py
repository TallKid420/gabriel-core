"""
NOTE: This is not PEEL, it is what the agent requests.
PEEL will later decide which requested capabilities are actually granted.
"""

class AgentCapabilities:
    requested: set[str]