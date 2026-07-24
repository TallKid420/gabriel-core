"""forward_email — forward an existing email to another address."""
from __future__ import annotations
from langchain_core.tools import tool
from email.message import EmailMessage
from typing import Any
from gabriel.tool.library.email._email_client import EmailClient


@tool
async def forward_email(
    email_id: str,
    to: str,
    _credentials: dict[str, Any] | None = None,
) -> dict:
    """Forward an email to a different recipient.

    Args:
        email_id:     The numeric IMAP message ID to forward.
        to:           Forwarding recipient address.
        _credentials: Injected by executor — org-scoped IMAP/SMTP credentials.

    Returns:
        ``{"status": "forwarded", "to": ...}`` or ``{"error": ...}``.
    """
    if not _credentials:
        return {"error": "Email credentials not configured for this org."}
    try:
        client = EmailClient(_credentials)
        original = client.fetch_email(email_id)
        if original is None:
            client.close()
            return {"error": f"Email {email_id} not found."}
        msg = EmailMessage()
        msg["From"] = client.username
        msg["To"] = to
        msg["Subject"] = "Fwd: " + client.decode_header_value(original["Subject"])
        msg.set_content(original.as_string())
        client.connect_smtp().send_message(msg)
        client.close()
        return {"status": "forwarded", "to": to}
    except Exception as exc:
        return {"error": str(exc)}
