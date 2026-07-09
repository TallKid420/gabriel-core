"""search_emails — search the inbox using an IMAP TEXT query."""
from __future__ import annotations
from typing import Any
from gabriel.tool.library.email._email_client import EmailClient


async def search_emails(
    query: str,
    _credentials: dict[str, Any] | None = None,
) -> dict:
    """Search emails by keyword using IMAP TEXT search.

    Args:
        query:        The keyword or phrase to search for.
        _credentials: Injected by executor — org-scoped IMAP/SMTP credentials.

    Returns:
        ``{"email_ids": [...], "count": N}`` or ``{"error": ...}``.
    """
    if not _credentials:
        return {"error": "Email credentials not configured for this org."}
    try:
        client = EmailClient(_credentials)
        imap = client.select_folder()
        _, data = imap.search(None, f'(TEXT "{query}")')
        ids = [x.decode() if isinstance(x, bytes) else x for x in data[0].split()]
        client.close()
        return {"email_ids": ids, "count": len(ids)}
    except Exception as exc:
        return {"error": str(exc)}
