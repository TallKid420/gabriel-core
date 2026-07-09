"""Org-scoped IMAP/SMTP email client.

This replaces the legacy ``executor/tools/email/_email_client.py`` which
pulled credentials from a global ``config.runtime.tool_manager``.

The new client accepts all credentials as constructor arguments.  Callers must
obtain credentials from :class:`~gabriel.integration.service.ExternalIntegrationService`
using the org's ``IntegrationType.IMAP_SMTP`` integration record.

Expected credentials dict keys
-------------------------------
imap_host     : str   — IMAP server hostname
imap_port     : int   — IMAP server port (default 993)
smtp_host     : str   — SMTP server hostname
smtp_port     : int   — SMTP server port (default 465)
username      : str   — login username / email address
password      : str   — login password / app password
use_ssl       : bool  — use SSL/TLS (default True)
default_folder: str   — default IMAP folder (default "INBOX")
"""

from __future__ import annotations

import email
import imaplib
import smtplib
from email.header import decode_header
from email.message import EmailMessage
from typing import Any


class EmailClient:
    """IMAP + SMTP client backed by org-scoped credentials."""

    def __init__(self, credentials: dict[str, Any]) -> None:
        self._imap_host: str = credentials["imap_host"]
        self._imap_port: int = int(credentials.get("imap_port", 993))
        self._smtp_host: str = credentials["smtp_host"]
        self._smtp_port: int = int(credentials.get("smtp_port", 465))
        self._username: str = credentials["username"]
        self._password: str = credentials["password"]
        self._use_ssl: bool = bool(credentials.get("use_ssl", True))
        self._default_folder: str = credentials.get("default_folder", "INBOX")

        self._imap: imaplib.IMAP4 | None = None
        self._smtp: smtplib.SMTP | None = None

    @property
    def username(self) -> str:
        return self._username

    # ------------------------------------------------------------------
    # IMAP
    # ------------------------------------------------------------------

    def connect_imap(self) -> imaplib.IMAP4:
        if self._imap:
            return self._imap
        if self._use_ssl:
            self._imap = imaplib.IMAP4_SSL(self._imap_host, self._imap_port)
        else:
            self._imap = imaplib.IMAP4(self._imap_host, self._imap_port)
        self._imap.login(self._username, self._password)
        return self._imap

    def select_folder(self, folder: str | None = None) -> imaplib.IMAP4:
        imap = self.connect_imap()
        imap.select(folder or self._default_folder)
        return imap

    def fetch_email(self, email_id: str | bytes) -> email.message.Message | None:
        imap = self.select_folder()
        status, data = imap.fetch(email_id, "(RFC822)")
        if status != "OK" or not data or data[0] is None:
            return None
        raw = data[0][1]  # type: ignore[index]
        return email.message_from_bytes(raw)

    def decode_header_value(self, value: str | None) -> str:
        if not value:
            return ""
        decoded_parts = decode_header(value)
        result = []
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                result.append(part.decode(charset or "utf-8", errors="ignore"))
            else:
                result.append(part)
        return "".join(result)

    # ------------------------------------------------------------------
    # SMTP
    # ------------------------------------------------------------------

    def connect_smtp(self) -> smtplib.SMTP:
        if self._smtp:
            return self._smtp
        if self._use_ssl:
            self._smtp = smtplib.SMTP_SSL(self._smtp_host, self._smtp_port)
        else:
            self._smtp = smtplib.SMTP(self._smtp_host, self._smtp_port)
        self._smtp.login(self._username, self._password)
        return self._smtp

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close open IMAP and SMTP connections."""
        try:
            if self._imap:
                self._imap.logout()
        except Exception:
            pass
        try:
            if self._smtp:
                self._smtp.quit()
        except Exception:
            pass
        self._imap = None
        self._smtp = None
