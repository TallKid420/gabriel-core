"""Core identity models: enums and domain objects."""
from enum import Enum


class PrincipalType(str, Enum):
    """Type of principal acting in the system."""

    USER = "user"
    AGENT = "agent"
    SYSTEM_AGENT = "system_agent"
    SERVICE_ACCOUNT = "service_account"


class PrincipalStatus(str, Enum):
    """Status/lifecycle state of a principal."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class Capability(str, Enum):
    """Capabilities a principal may have.
    
    Note: These are NOT permissions.
    Permissions come later through PEEL (Policy Expression Evaluation Language).
    
    Capabilities describe what a principal type is *capable* of doing.
    PEEL will determine what they're *allowed* to do.
    """

    # Core capabilities
    AUTHENTICATE = "authenticate"  # Can authenticate and receive tokens
    READ_ORGANIZATION = "read_organization"  # Can read organization metadata
    READ_PRINCIPAL = "read_principal"  # Can read principal metadata (self + org)
    EXECUTE_WORKFLOW = "execute_workflow"  # Can execute workflows/agents
    CALL_TOOL = "call_tool"  # Can invoke external tools
    FILE_READ = "file_read"  # Can read org-scoped files via file tools
    FILE_WRITE = "file_write"  # Can write org-scoped files via file tools
    READ_RESOURCE = "read_resource"  # Can read resources in org
    WRITE_RESOURCE = "write_resource"  # Can create/update resources

    # Advanced capabilities
    MANAGE_PRINCIPALS = "manage_principals"  # Can create/suspend principals
    MANAGE_POLICIES = "manage_policies"  # Can define PEEL policies
    AUDIT_LOG = "audit_log"  # Can read audit logs
    SYSTEM_ADMIN = "system_admin"  # Full system access (rarely used)
