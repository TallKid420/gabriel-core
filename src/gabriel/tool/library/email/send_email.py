"""send_email — send an email via SMTP."""
from __future__ import annotations
from langchain_core.tools import tool
from email.message import EmailMessage
from typing import Any
from gabriel.tool.library.email._email_client import EmailClient


@tool
async def send_email(
    to: str,
    subject: str,
    body: str,
    _credentials: dict[str, Any] | None = None,
) -> dict:
    """Send an email.

    Args:
        to:           Recipient address.
        subject:      Email subject line.
        body:         Plain-text body.
        _credentials: Injected by executor — org-scoped IMAP/SMTP credentials.

    Returns:
        ``{"status": "sent", "to": ...}`` or ``{"error": ...}``.
    """
    if not _credentials:
        return {"error": "Email credentials not configured for this org."}
    try:
        client = EmailClient(_credentials)
        msg = EmailMessage()
        msg["From"] = client.username
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        client.connect_smtp().send_message(msg)
        client.close()
        return {"status": "sent", "to": to}
    except Exception as exc:
        return {"error": str(exc)}
