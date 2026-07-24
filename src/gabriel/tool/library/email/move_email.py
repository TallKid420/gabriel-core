"""move_email — move an email to another IMAP folder."""
from __future__ import annotations
from langchain_core.tools import tool
from typing import Any
from gabriel.tool.library.email._email_client import EmailClient


@tool
async def move_email(
    email_id: str,
    destination: str,
    _credentials: dict[str, Any] | None = None,
) -> dict:
    """Move an email to another IMAP folder.

    Copies the email to *destination*, then marks the source as deleted and
    expunges, effectively performing a move.

    Args:
        email_id:     The numeric IMAP message ID.
        destination:  Target folder name (e.g. ``"Archive"``, ``"[Gmail]/All Mail"``).
        _credentials: Injected by executor — org-scoped IMAP/SMTP credentials.

    Returns:
        ``{"status": "moved", "destination": ..., "email_id": ...}`` or ``{"error": ...}``.
    """
    if not _credentials:
        return {"error": "Email credentials not configured for this org."}
    try:
        client = EmailClient(_credentials)
        imap = client.select_folder()
        result = imap.copy(email_id, destination)
        if result[0] == "OK":
            imap.store(email_id, "+FLAGS", "\\Deleted")
            imap.expunge()
        client.close()
        return {"status": "moved", "destination": destination, "email_id": email_id}
    except Exception as exc:
        return {"error": str(exc)}
