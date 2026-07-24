"""find_file — search for documents in the org's content store by filename pattern.

This tool is org-scoped: it can only access documents that belong to the
calling principal's organization.  Cross-org access is structurally impossible
because the ``org_id`` is sourced from the caller's ExecutionContext, not from
user input.

Note: The ``org_id`` is injected by the ToolExecutor at call-time via the
``_org_id`` meta-argument that the executor adds to tool arguments when the
Tool's ``runtime_binding`` starts with ``"file."``.  Tool authors should treat
``_org_id`` as a trusted, executor-controlled argument — callers cannot
override it.
"""

from __future__ import annotations
from langchain_core.tools import tool

import fnmatch
from pathlib import Path


@tool
async def find_file(
    pattern: str,
    _org_id: str = "",
    _content_root: str = "/var/gabriel/content",
) -> dict:
    """Find files matching a glob pattern in the org's document storage.

    The search is restricted to ``{_content_root}/{_org_id}/documents/``.
    Pattern matching uses Unix shell-style globs (fnmatch).

    Args:
        pattern:        Glob pattern, e.g. ``"*.txt"``, ``"report_*"``.
        _org_id:        Injected by executor — org boundary (do not pass manually).
        _content_root:  Injected by executor — storage root path.

    Returns:
        ``{"matches": [...], "count": N}`` or ``{"error": ...}``.
    """
    if not _org_id:
        return {"error": "org_id is required (executor injection missing)"}

    search_root = Path(_content_root) / _org_id / "documents"
    if not search_root.exists():
        return {"matches": [], "count": 0}

    try:
        matches = [
            str(p.relative_to(search_root))
            for p in search_root.iterdir()
            if p.is_file() and fnmatch.fnmatch(p.name, pattern)
        ]
        matches.sort()
        return {"matches": matches, "count": len(matches)}
    except Exception as exc:
        return {"error": f"find_file failed: {exc}"}
