"""Email tool library — self-registers at import time.

Requires an active IMAP_SMTP ExternalIntegration record for the calling org.
Credentials are injected by the ToolExecutor via ``_credentials``.

All write operations (send, draft, reply, forward, archive, delete, label, move)
carry ``SafetyLevel.REQUIRES_CONFIRMATION`` in the seed data and must be
explicitly confirmed by the calling agent before dispatch.
"""

from gabriel.tool.library.email.archive_email import archive_email
from gabriel.tool.library.email.delete_email import delete_email
from gabriel.tool.library.email.draft_email import draft_email
from gabriel.tool.library.email.forward_email import forward_email
from gabriel.tool.library.email.get_email import get_email
from gabriel.tool.library.email.get_thread import get_thread
from gabriel.tool.library.email.label_email import label_email
from gabriel.tool.library.email.list_emails import list_emails
from gabriel.tool.library.email.mark_email import mark_email
from gabriel.tool.library.email.move_email import move_email
from gabriel.tool.library.email.reply_email import reply_email
from gabriel.tool.library.email.search_emails import search_emails
from gabriel.tool.library.email.send_email import send_email
from gabriel.tool.registry import function_registry

function_registry.register_many(
    {
        "integration.gmail.send_email": send_email,
        "integration.gmail.list_emails": list_emails,
        "integration.gmail.get_email": get_email,
        "integration.gmail.draft_email": draft_email,
        "integration.gmail.reply_email": reply_email,
        "integration.gmail.forward_email": forward_email,
        "integration.gmail.archive_email": archive_email,
        "integration.gmail.mark_email": mark_email,
        "integration.gmail.delete_email": delete_email,
        "integration.gmail.label_email": label_email,
        "integration.gmail.move_email": move_email,
        "integration.gmail.search_emails": search_emails,
        "integration.gmail.get_thread": get_thread,
    }
)

__all__ = [
    "archive_email",
    "delete_email",
    "draft_email",
    "forward_email",
    "get_email",
    "get_thread",
    "label_email",
    "list_emails",
    "mark_email",
    "move_email",
    "reply_email",
    "search_emails",
    "send_email",
]
