"""Organization roles and their capability grants (role-based access control).

Roles are the coarse, human-facing layer of the PEEL authorization model:

* A role is attached to an organization *membership* (a user's seat in an org).
* Each role expands to a set of :class:`~gabriel.identity.models.Capability`
  values which are stamped onto the member's Principal (identity-based PEEL
  enforcement, the fail-secure default).
* Fine-grained, resource-level permissions remain the domain of explicit
  Policy statements evaluated by the PolicyEngine (policy-based enforcement).

This keeps the two PEEL layers cleanly separated: roles → capabilities
(what kind of actor you are), policies → permissions (what exactly you may
touch).
"""
from __future__ import annotations

from enum import Enum

from gabriel.identity.models import Capability


class OrgRole(str, Enum):
    """A member's role within an organization."""

    OWNER = "owner"
    """Full control of the organization, including managing other members."""

    ADMIN = "admin"
    """Manage principals and policies; full resource access."""

    MEMBER = "member"
    """Create/read/update resources and execute workflows."""

    VIEWER = "viewer"
    """Read-only access to organization resources."""


_BASE_CAPABILITIES: frozenset[Capability] = frozenset(
    {
        Capability.AUTHENTICATE,
        Capability.READ_ORGANIZATION,
        Capability.READ_PRINCIPAL,
    }
)

ROLE_CAPABILITIES: dict[OrgRole, frozenset[Capability]] = {
    OrgRole.VIEWER: _BASE_CAPABILITIES
    | frozenset({Capability.READ_RESOURCE}),
    OrgRole.MEMBER: _BASE_CAPABILITIES
    | frozenset(
        {
            Capability.READ_RESOURCE,
            Capability.WRITE_RESOURCE,
            Capability.EXECUTE_WORKFLOW,
            Capability.CALL_TOOL,
            Capability.FILE_READ,
            Capability.FILE_WRITE,
        }
    ),
    OrgRole.ADMIN: _BASE_CAPABILITIES
    | frozenset(
        {
            Capability.READ_RESOURCE,
            Capability.WRITE_RESOURCE,
            Capability.EXECUTE_WORKFLOW,
            Capability.CALL_TOOL,
            Capability.FILE_READ,
            Capability.FILE_WRITE,
            Capability.MANAGE_PRINCIPALS,
            Capability.MANAGE_POLICIES,
            Capability.AUDIT_LOG,
        }
    ),
}
# OWNER: everything ADMIN has. SYSTEM_ADMIN is intentionally NOT granted by any
# org role — it is a platform-operator capability assigned out-of-band.
ROLE_CAPABILITIES[OrgRole.OWNER] = ROLE_CAPABILITIES[OrgRole.ADMIN]

# Role dominance order used when a principal holds multiple memberships or a
# role change needs "at least as powerful" comparisons.
ROLE_ORDER: dict[OrgRole, int] = {
    OrgRole.VIEWER: 0,
    OrgRole.MEMBER: 1,
    OrgRole.ADMIN: 2,
    OrgRole.OWNER: 3,
}


def capabilities_for_role(role: OrgRole | str) -> set[Capability]:
    """Return the capability set granted by ``role``."""
    normalized = role if isinstance(role, OrgRole) else OrgRole(role)
    return set(ROLE_CAPABILITIES[normalized])


def role_at_least(role: OrgRole | str, minimum: OrgRole) -> bool:
    """Return True if ``role`` is at least as powerful as ``minimum``."""
    normalized = role if isinstance(role, OrgRole) else OrgRole(role)
    return ROLE_ORDER[normalized] >= ROLE_ORDER[minimum]
