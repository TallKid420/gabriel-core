"""
Everything should eventually execute from events.
Examples: 
    - OrganizationCreated 
    - MemoryWritten 
    - UserMessageReceived 
    - ToolCompleted
"""

class Trigger:
    event_type: str
    filter: dict[str, str]