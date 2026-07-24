"""get_thread — retrieve all emails in a thread by matching subject."""
from __future__ import annotations
from langchain_core.tools import tool
from typing import Any
from gabriel.tool.library.email._email_client import EmailClient


@tool
async def get_thread(
    email_id: str,
    _credentials: dict[str, Any] | None = None,
) -> dict:
    """Retrieve related emails in a thread by searching for matching subjects.

    This uses an IMAP SUBJECT search as a heuristic.  Emails sharing the same
    (stripped) subject are treated as belonging to the same thread.

    Args:
        email_id:     Seed email ID whose subject defines the thread.
        _credentials: Injected by executor — org-scoped IMAP/SMTP credentials.

    Returns:
        ``{"thread": [...], "count": N}`` or ``{"error": ...}``.
    """
    if not _credentials:
        return {"error": "Email credentials not configured for this org."}
    try:
        client = EmailClient(_credentials)
        original = client.fetch_email(email_id)
        if original is None:
            client.close()
            return {"error": f"Email {email_id} not found."}

        subject = client.decode_header_value(original["Subject"])
        # Strip Re:/Fwd: prefixes for better matching
        import re
        clean_subject = re.sub(r"^(Re:|Fwd:)\s*", "", subject, flags=re.IGNORECASE).strip()

        imap = client.select_folder()
        _, data = imap.search(None, f'(SUBJECT "{clean_subject}")')
        thread_emails = []
        for item in data[0].split():
            msg = client.fetch_email(item)
            if msg is None:
                continue
            thread_emails.append({
                "id": item.decode() if isinstance(item, bytes) else item,
                "from": msg["From"],
                "subject": client.decode_header_value(msg["Subject"]),
                "date": msg["Date"],
            })
        client.close()
        return {"thread": thread_emails, "count": len(thread_emails)}
    except Exception as exc:
        return {"error": str(exc)}
