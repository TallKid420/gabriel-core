"""list_emails — list recent emails from the inbox."""
from __future__ import annotations
from typing import Any
from gabriel.tool.library.email._email_client import EmailClient


async def list_emails(
    limit: int = 10,
    _credentials: dict[str, Any] | None = None,
) -> dict:
    """List recent emails from the default folder.

    Args:
        limit:        Maximum number of emails to return (default 10).
        _credentials: Injected by executor — org-scoped IMAP/SMTP credentials.

    Returns:
        ``{"emails": [...], "count": N}`` or ``{"error": ...}``.
    """
    if not _credentials:
        return {"error": "Email credentials not configured for this org."}
    try:
        client = EmailClient(_credentials)
        imap = client.select_folder()
        _, data = imap.search(None, "ALL")
        ids = data[0].split()
        results = []
        for email_id in ids[-limit:]:
            msg = client.fetch_email(email_id)
            if msg is None:
                continue
            results.append({
                "id": email_id.decode() if isinstance(email_id, bytes) else email_id,
                "subject": client.decode_header_value(msg["Subject"]),
                "from": msg["From"],
                "date": msg["Date"],
            })
        client.close()
        return {"emails": results, "count": len(results)}
    except Exception as exc:
        return {"error": str(exc)}
