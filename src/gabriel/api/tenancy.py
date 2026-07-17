"""Shared tenant-isolation guards for API routers.

Previously every router carried its own copy of ``_require_same_org`` (eight
duplicates). This module is the single source of truth (ADR-011 module
boundary hygiene; F-001 tenant isolation at the API edge).
"""
from __future__ import annotations

from gabriel.api.errors import GabrielAPIError
from gabriel.resource.grn import GRN
from gabriel.runtime.context import ExecutionContext


def require_same_org(context: ExecutionContext, grn_str: str) -> GRN:
    """Reject GRNs that address a different tenant.

    Raises:
        GabrielAPIError: 422 for a malformed GRN, 403 for cross-tenant access.

    Returns:
        The parsed :class:`GRN` for convenience.
    """
    try:
        grn = GRN.parse(grn_str)
    except Exception as exc:
        raise GabrielAPIError(f"Invalid GRN '{grn_str}'", status_code=422) from exc
    if grn.org_id != context.organization:
        raise GabrielAPIError(
            "Cross-organization access is forbidden", status_code=403
        )
    return grn
