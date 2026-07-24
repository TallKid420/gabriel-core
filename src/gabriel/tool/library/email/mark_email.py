"""mark_email — mark an email as read or unread."""
from __future__ import annotations
from langchain_core.tools import tool
from typing import Any
from gabriel.tool.library.email._email_client import EmailClient


@tool
async def mark_email(
    email_id: str,
    read: bool = True,
    _credentials: dict[str, Any] | None = None,
) -> dict:
    """Mark an email as read or unread.

    Args:
        email_id:     The numeric IMAP message ID.
        read:         ``True`` to mark as read, ``False`` for unread (default True).
        _credentials: Injected by executor — org-scoped IMAP/SMTP credentials.

    Returns:
        ``{"email_id": ..., "read": ...}`` or ``{"error": ...}``.
    """
    if not _credentials:
        return {"error": "Email credentials not configured for this org."}
    try:
        client = EmailClient(_credentials)
        imap = client.select_folder()
        flag_op = "+FLAGS" if read else "-FLAGS"
        imap.store(email_id, flag_op, "\\Seen")
        client.close()
        return {"email_id": email_id, "read": read}
    except Exception as exc:
        return {"error": str(exc)}
