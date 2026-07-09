"""get_email — retrieve the full contents of a single email."""
from __future__ import annotations
from typing import Any
from gabriel.tool.library.email._email_client import EmailClient


async def get_email(
    email_id: str,
    _credentials: dict[str, Any] | None = None,
) -> dict:
    """Get the full content of an email by ID.

    Args:
        email_id:     The numeric IMAP message ID (as returned by list_emails).
        _credentials: Injected by executor — org-scoped IMAP/SMTP credentials.

    Returns:
        ``{"from", "subject", "body"}`` or ``{"error": ...}``.
    """
    if not _credentials:
        return {"error": "Email credentials not configured for this org."}
    try:
        client = EmailClient(_credentials)
        msg = client.fetch_email(email_id)
        if msg is None:
            client.close()
            return {"error": f"Email {email_id} not found."}
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body += part.get_payload(decode=True).decode(errors="ignore")
        else:
            body = msg.get_payload(decode=True).decode(errors="ignore")
        client.close()
        return {
            "from": msg["From"],
            "subject": client.decode_header_value(msg["Subject"]),
            "date": msg["Date"],
            "body": body,
        }
    except Exception as exc:
        return {"error": str(exc)}
