"""archive_email — remove an email from the inbox."""
from __future__ import annotations
from langchain_core.tools import tool
from typing import Any
from gabriel.tool.library.email._email_client import EmailClient


@tool
async def archive_email(
    email_id: str,
    _credentials: dict[str, Any] | None = None,
) -> dict:
    """Archive an email by removing its \\Inbox flag.

    Args:
        email_id:     The numeric IMAP message ID to archive.
        _credentials: Injected by executor — org-scoped IMAP/SMTP credentials.

    Returns:
        ``{"status": "archived", "email_id": ...}`` or ``{"error": ...}``.
    """
    if not _credentials:
        return {"error": "Email credentials not configured for this org."}
    try:
        client = EmailClient(_credentials)
        imap = client.select_folder()
        imap.store(email_id, "-FLAGS", "\\Inbox")
        client.close()
        return {"status": "archived", "email_id": email_id}
    except Exception as exc:
        return {"error": str(exc)}
