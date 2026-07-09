"""label_email — add a label (Gmail-specific) to an email."""
from __future__ import annotations
from typing import Any
from gabriel.tool.library.email._email_client import EmailClient


async def label_email(
    email_id: str,
    label: str,
    _credentials: dict[str, Any] | None = None,
) -> dict:
    """Add a Gmail label to an email via the X-GM-LABELS IMAP extension.

    Note: This is Gmail-specific.  Other IMAP servers will return an error.

    Args:
        email_id:     The numeric IMAP message ID.
        label:        Gmail label name to apply (e.g. ``"Important"``).
        _credentials: Injected by executor — org-scoped IMAP/SMTP credentials.

    Returns:
        ``{"status": "label_added", "label": ..., "email_id": ...}`` or ``{"error": ...}``.
    """
    if not _credentials:
        return {"error": "Email credentials not configured for this org."}
    try:
        client = EmailClient(_credentials)
        imap = client.select_folder()
        imap.store(email_id, "+X-GM-LABELS", label)
        client.close()
        return {"status": "label_added", "label": label, "email_id": email_id}
    except Exception as exc:
        return {"error": str(exc)}
