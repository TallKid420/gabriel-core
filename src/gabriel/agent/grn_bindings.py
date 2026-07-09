"""GRN-based tool bindings for agent specifications.

Legacy Gabriel agents referenced tools by bare slugs (``get_time``, ``calculate``)
stored in ``agents.yaml``. Gabriel Core models every tool as a *Resource* with a
GRN (Gabriel Resource Name) — see ADR-009 (GRN Factory) and the Universal
Resource Model. Phase 4 migrates agent tool references onto GRN-formatted
bindings so an ``AgentSpecification`` declares tools the same way every other
resource is referenced.

Binding format
--------------
    grn:<org_id>:tool/<tool_name>:<version>

Wildcards (``*``) are permitted for ``org_id`` and ``version`` inside an agent
*template*, because a template is org-agnostic and version-agnostic until it is
instantiated for a concrete organization::

    grn:*:tool/get_time:*          # template binding (any org, any version)
    grn:acme:tool/get_time:1       # concrete binding (resolved at deploy time)

This module deliberately does NOT reuse :class:`gabriel.resource.grn.GRN`
because that type requires a concrete integer version and a concrete org id.
Tool bindings are *patterns* that get resolved to a concrete ``GRN`` when the
template is instantiated for an org.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

WILDCARD = "*"
TOOL_RESOURCE_TYPE = "tool"

# grn:<org>:tool/<name>:<version>  — org & version may be "*"
_TOOL_GRN_RE = re.compile(
    r"^grn:(?P<org>[^:]+):tool/(?P<name>[^:/]+):(?P<version>\*|\d+)$"
)


@dataclass(frozen=True)
class ToolBinding:
    """A parsed tool GRN binding."""

    name: str
    org_id: str = WILDCARD
    version: str = WILDCARD

    def to_grn(self) -> str:
        """Render the binding back to its GRN string form."""
        return f"grn:{self.org_id}:{TOOL_RESOURCE_TYPE}/{self.name}:{self.version}"

    def resolve(self, org_id: str, version: int = 1) -> str:
        """Resolve a wildcard template binding to a concrete tool GRN."""
        org = self.org_id if self.org_id != WILDCARD else org_id
        ver = self.version if self.version != WILDCARD else str(version)
        return f"grn:{org}:{TOOL_RESOURCE_TYPE}/{self.name}:{ver}"

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.to_grn()


def tool_grn(name: str, org_id: str = WILDCARD, version: str | int = WILDCARD) -> str:
    """Build a tool-binding GRN string.

    Args:
        name: Tool slug, e.g. ``"get_time"``.
        org_id: Owning org, or ``"*"`` for a template (default).
        version: Version number, or ``"*"`` for a template (default).

    Returns:
        A GRN string such as ``"grn:*:tool/get_time:*"``.
    """
    if not name or not name.strip():
        raise ValueError("tool name must not be empty")
    return f"grn:{org_id}:{TOOL_RESOURCE_TYPE}/{name}:{version}"


def is_tool_grn(value: str) -> bool:
    """Return True if *value* is a well-formed tool-binding GRN."""
    return bool(_TOOL_GRN_RE.match(value))


def parse_tool_grn(value: str) -> ToolBinding:
    """Parse a tool-binding GRN into a :class:`ToolBinding`.

    Raises:
        ValueError: if *value* is not a well-formed tool-binding GRN.
    """
    match = _TOOL_GRN_RE.match(value)
    if not match:
        raise ValueError(f"Malformed tool GRN: {value!r}")
    return ToolBinding(
        name=match.group("name"),
        org_id=match.group("org"),
        version=match.group("version"),
    )


def tool_name(value: str) -> str:
    """Extract the bare tool slug from a tool-binding GRN.

    Accepts either a GRN (``grn:*:tool/get_time:*``) or a bare slug
    (``get_time``) for backwards compatibility with legacy specs.
    """
    if is_tool_grn(value):
        return parse_tool_grn(value).name
    return value


def resolve_tools(bindings: list[str], org_id: str, version: int = 1) -> list[str]:
    """Resolve a list of (possibly wildcard) tool bindings for a concrete org.

    Bare slugs are upgraded to GRN form; already-concrete GRNs are preserved.
    """
    resolved: list[str] = []
    for binding in bindings:
        if is_tool_grn(binding):
            resolved.append(parse_tool_grn(binding).resolve(org_id, version))
        else:
            # bare legacy slug -> concrete GRN
            resolved.append(tool_grn(binding, org_id, version))
    return resolved
