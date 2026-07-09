"""delete_email — permanently delete an email."""
from __future__ import annotations
from typing import Any
from gabriel.tool.library.email._email_client import EmailClient


async def delete_email(
    email_id: str,
    _credentials: dict[str, Any] | None = None,
) -> dict:
    """Permanently delete an email (sets \\Deleted flag and expunges).

    Args:
        email_id:     The numeric IMAP message ID to delete.
        _credentials: Injected by executor — org-scoped IMAP/SMTP credentials.

    Returns:
        ``{"status": "deleted", "email_id": ...}`` or ``{"error": ...}``.
    """
    if not _credentials:
        return {"error": "Email credentials not configured for this org."}
    try:
        client = EmailClient(_credentials)
        imap = client.select_folder()
        imap.store(email_id, "+FLAGS", "\\Deleted")
        imap.expunge()
        client.close()
        return {"status": "deleted", "email_id": email_id}
    except Exception as exc:
        return {"error": str(exc)}
