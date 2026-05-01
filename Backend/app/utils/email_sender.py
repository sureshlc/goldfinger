"""
Lightweight SMTP email sender. Built for AWS SES SMTP but works with any
RFC-5321 SMTP relay supporting STARTTLS on port 587 (or implicit TLS on 465).

Synchronous by design — wrap calls with `asyncio.to_thread` from async code.
"""
from __future__ import annotations

import logging
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Iterable, List, Optional, Tuple

from app.config import Settings

logger = logging.getLogger(__name__)


class EmailNotConfiguredError(RuntimeError):
    """Raised when SMTP credentials are not present in settings."""


def _build_message(
    sender: str,
    to: Iterable[str],
    subject: str,
    html_body: str,
    text_body: Optional[str],
    attachments: List[Tuple[str, bytes, str]],
) -> MIMEMultipart:
    msg = MIMEMultipart("mixed")
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject

    body = MIMEMultipart("alternative")
    if text_body:
        body.attach(MIMEText(text_body, "plain", "utf-8"))
    body.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(body)

    for filename, content, mime in attachments:
        # Allow callers to pass full mime types like "text/csv".
        maintype, _, subtype = mime.partition("/")
        if maintype == "text":
            part = MIMEText(content.decode("utf-8", errors="replace"), subtype or "plain", "utf-8")
        else:
            part = MIMEApplication(content, _subtype=subtype or "octet-stream")
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)

    return msg


def send_email(
    settings: Settings,
    to: List[str],
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    attachments: Optional[List[Tuple[str, bytes, str]]] = None,
) -> None:
    """Send an email via SMTP. Raises EmailNotConfiguredError if settings are incomplete."""
    if not settings.email_configured:
        raise EmailNotConfiguredError(
            "SMTP is not configured. Set SMTP_HOST/SMTP_USERNAME/SMTP_PASSWORD/SMTP_FROM."
        )
    if not to:
        raise ValueError("At least one recipient is required.")

    sender = formataddr(("Agent Goldfinger", settings.smtp_from))
    msg = _build_message(sender, to, subject, html_body, text_body, attachments or [])

    logger.info(
        "Sending email via %s:%s to %d recipient(s) — subject=%r",
        settings.smtp_host,
        settings.smtp_port,
        len(to),
        subject,
    )

    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.sendmail(settings.smtp_from, to, msg.as_string())
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            smtp.ehlo()
            if settings.smtp_use_tls:
                smtp.starttls()
                smtp.ehlo()
            smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.sendmail(settings.smtp_from, to, msg.as_string())
