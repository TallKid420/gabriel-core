"""Execution capabilities: What principals are capable of doing.

Note: Capabilities describe what a principal *can* do.
Permissions (whether they *should* do it) come from PEEL.
"""
from enum import Enum


class Capability(str, Enum):
    """Capabilities a principal may have.
    
    A capability is a descriptor of what a principal is capable of doing.
    PEEL policies then determine whether they *should* exercise a capability
    against a specific resource.
    
    Example:
    - Principal has capability READ_MEMORY
    - But PEEL policy may deny reading a specific memory object
    """

    # Memory operations
    READ_MEMORY = "read_memory"
    """Can read from memory storage."""

    WRITE_MEMORY = "write_memory"
    """Can write to memory storage."""

    # Tool operations
    INVOKE_TOOL = "invoke_tool"
    """Can invoke external tools."""

    # Resource operations
    CREATE_RESOURCE = "create_resource"
    """Can create resources."""

    DELETE_RESOURCE = "delete_resource"
    """Can delete resources."""

    UPDATE_RESOURCE = "update_resource"
    """Can update resource state."""

    # Event operations
    CREATE_EVENT = "create_event"
    """Can emit events."""

    # Execution operations
    EXECUTE_AGENT = "execute_agent"
    """Can execute agents/workflows."""

    SCHEDULE_EXECUTION = "schedule_execution"
    """Can schedule executions."""

    CANCEL_EXECUTION = "cancel_execution"
    """Can cancel running executions."""

    # System operations
    VIEW_AUDIT_LOG = "view_audit_log"
    """Can access audit logs."""

    MANAGE_POLICIES = "manage_policies"
    """Can define or modify PEEL policies."""
