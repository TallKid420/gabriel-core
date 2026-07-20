"""Email tool library — discovered by :class:`gabriel.tool.discovery.ToolLibraryIndexer`.

Requires an active IMAP_SMTP ExternalIntegration record for the calling org.
Credentials are injected by the ToolExecutor via ``_credentials``.

All write operations (send, draft, reply, forward, archive, delete, label, move)
carry ``SafetyLevel.REQUIRES_CONFIRMATION`` in the seed data and must be
explicitly confirmed by the calling agent before dispatch.
"""

from .archive_email import archive_email
from .delete_email import delete_email
from .draft_email import draft_email
from .forward_email import forward_email
from .get_email import get_email
from .get_thread import get_thread
from .label_email import label_email
from .list_emails import list_emails
from .mark_email import mark_email
from .move_email import move_email
from .reply_email import reply_email
from .search_emails import search_emails
from .send_email import send_email

TOOL_NAMESPACE = "integration.gmail"

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
