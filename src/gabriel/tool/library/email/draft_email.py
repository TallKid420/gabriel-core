"""draft_email — save an email to the Drafts folder."""
from __future__ import annotations
from langchain_core.tools import tool
from email.message import EmailMessage
from typing import Any
from gabriel.tool.library.email._email_client import EmailClient


@tool
async def draft_email(
    to: str,
    subject: str,
    body: str,
    _credentials: dict[str, Any] | None = None,
) -> dict:
    """Create an email draft in the [Gmail]/Drafts folder.

    Args:
        to:           Intended recipient address.
        subject:      Email subject line.
        body:         Plain-text body.
        _credentials: Injected by executor — org-scoped IMAP/SMTP credentials.

    Returns:
        ``{"status": "draft_created"}`` or ``{"error": ...}``.
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

        imap = client.connect_imap()
        imap.append("[Gmail]/Drafts", "\\Draft", None, msg.as_bytes())
        client.close()
        return {"status": "draft_created"}
    except Exception as exc:
        return {"error": str(exc)}
