"""SMTP email notifications for guest article usage."""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from weeklyamp.core.models import AppConfig

log = logging.getLogger(__name__)


def send_usage_notification(
    config: AppConfig,
    contact_name: str,
    contact_email: str,
    article_title: str,
    article_url: str,
) -> bool:
    """Send a polite email confirming we're featuring their content.

    Returns True if sent, False if skipped or failed.
    """
    if not contact_email:
        log.debug("No email for %s, skipping notification", contact_name)
        return False

    email_cfg = config.email
    if not email_cfg.enabled:
        log.info(
            "Email not configured — would notify %s <%s> about '%s'",
            contact_name, contact_email, article_title,
        )
        return False

    if not email_cfg.smtp_host or not email_cfg.from_address:
        log.warning("Email enabled but SMTP not fully configured")
        return False

    subject = f"Your content is being featured in {config.newsletter.name}"
    body_html = f"""\
<p>Hi {contact_name},</p>

<p>We wanted to let you know that we're featuring your article
<strong>"{article_title}"</strong> in an upcoming issue of
<strong>{config.newsletter.name}</strong>.</p>

<p>Full attribution and a link back to the original will be included:</p>
<p><a href="{article_url}">{article_url}</a></p>

<p>Thank you for creating great content that benefits our community of
independent artists and songwriters!</p>

<p>Best regards,<br>{email_cfg.from_name}</p>
"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{email_cfg.from_name} <{email_cfg.from_address}>"
    msg["To"] = contact_email
    msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP(email_cfg.smtp_host, email_cfg.smtp_port) as server:
            server.starttls()
            if email_cfg.smtp_user and email_cfg.smtp_password:
                server.login(email_cfg.smtp_user, email_cfg.smtp_password)
            server.send_message(msg)
        log.info("Sent usage notification to %s <%s>", contact_name, contact_email)
        return True
    except Exception as e:
        log.error("Failed to send email to %s: %s", contact_email, e)
        return False
