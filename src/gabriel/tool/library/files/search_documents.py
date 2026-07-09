"""search_documents — full-text keyword search over org-scoped documents.

Org-scoped: the search is restricted to documents belonging to the calling
principal's organization.  ``_org_id`` is injected by the ToolExecutor.
"""

from __future__ import annotations

from pathlib import Path


async def search_documents(
    query: str,
    limit: int = 10,
    _org_id: str = "",
    _content_root: str = "/var/gabriel/content",
) -> dict:
    """Search document content for a keyword or phrase.

    Performs a simple case-insensitive substring scan over all ``.txt`` files
    in the org's document storage directory.  For semantic / vector search, use
    :func:`~gabriel.tool.library.files.semantic_search.semantic_search` instead.

    Args:
        query:          Keyword or phrase to search for.
        limit:          Maximum number of results to return (default 10).
        _org_id:        Injected by executor — org boundary.
        _content_root:  Injected by executor — storage root path.

    Returns:
        ``{"results": [{"file", "excerpt", "line_number"}, ...], "count": N}``
        or ``{"error": ...}``.
    """
    if not _org_id:
        return {"error": "org_id is required (executor injection missing)"}
    if not query.strip():
        return {"error": "query must not be empty"}

    search_root = Path(_content_root) / _org_id / "documents"
    if not search_root.exists():
        return {"results": [], "count": 0}

    results: list[dict] = []
    q_lower = query.lower()

    try:
        for path in sorted(search_root.glob("*.txt")):
            if len(results) >= limit:
                break
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
                for line_no, line in enumerate(lines, start=1):
                    if q_lower in line.lower():
                        results.append(
                            {
                                "file": path.name,
                                "line_number": line_no,
                                "excerpt": line.strip()[:200],
                            }
                        )
                        if len(results) >= limit:
                            break
            except OSError:
                continue

        return {"results": results, "count": len(results)}
    except Exception as exc:
        return {"error": f"search_documents failed: {exc}"}
