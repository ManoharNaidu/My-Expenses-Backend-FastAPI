import logging
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from core.config import (
    BREVO_SENDER_EMAIL,
    BREVO_SENDER_NAME,
    BREVO_SMTP_HOST,
    BREVO_SMTP_PASSWORD,
    BREVO_SMTP_PORT,
    BREVO_SMTP_USER,
)

logger = logging.getLogger(__name__)

_SMTP_RETRIES = 2
_SMTP_RETRY_DELAY = 2  # seconds


def _send_email(
    to_email: str,
    subject: str,
    body_plain: str,
    body_html: Optional[str] = None,
) -> None:
    """Send an email via Brevo SMTP (STARTTLS on port 587).

    Supports both plain-text and optional HTML body. Falls back gracefully
    to plain-text for clients that don't render HTML. Retries up to
    _SMTP_RETRIES times on transient SMTP errors.

    Args:
        to_email:    Recipient email address.
        subject:     Email subject line.
        body_plain:  Plain-text version of the message (always required).
        body_html:   Optional HTML version of the message.
    """
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{BREVO_SENDER_NAME} <{BREVO_SENDER_EMAIL}>"
    msg["To"] = to_email

    # Plain-text part must come first; email clients prefer the last matching part.
    msg.attach(MIMEText(body_plain, "plain"))
    if body_html:
        msg.attach(MIMEText(body_html, "html"))

    last_exc: Optional[Exception] = None
    for attempt in range(1, _SMTP_RETRIES + 1):
        try:
            with smtplib.SMTP(BREVO_SMTP_HOST, BREVO_SMTP_PORT, timeout=10) as server:
                server.ehlo()
                server.starttls()
                # Re-identify after upgrading to TLS — required by some servers.
                server.ehlo()
                server.login(BREVO_SMTP_USER, BREVO_SMTP_PASSWORD)
                server.sendmail(BREVO_SENDER_EMAIL, to_email, msg.as_string())
            logger.info("Email sent to %s (attempt %d)", to_email, attempt)
            return
        except smtplib.SMTPAuthenticationError:
            # Auth errors are permanent — don't retry.
            logger.error("SMTP authentication failed. Check BREVO_SMTP_LOGIN / BREVO_SMTP_PASSWORD.")
            raise
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Failed to send email to %s on attempt %d/%d: %s",
                to_email, attempt, _SMTP_RETRIES, exc,
            )
            if attempt < _SMTP_RETRIES:
                time.sleep(_SMTP_RETRY_DELAY)

    logger.error("All %d SMTP attempts failed for %s", _SMTP_RETRIES, to_email)
    raise last_exc  # type: ignore[misc]


def send_verification_email(to_email: str, otp: str) -> None:
    subject = f"Verify your {BREVO_SENDER_NAME} account"
    body_plain = (
        f"Your verification code is: {otp}\n\n"
        "This code will expire in 10 minutes.\n\n"
        f"If you did not request this, please ignore this email."
    )
    body_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333;">
        <h2>Verify your {BREVO_SENDER_NAME} account</h2>
        <p>Use the code below to verify your email address:</p>
        <p style="font-size: 2em; font-weight: bold; letter-spacing: 4px;">{otp}</p>
        <p>This code will expire in <strong>10 minutes</strong>.</p>
        <hr/>
        <p style="font-size: 0.85em; color: #888;">
          If you did not request this, please ignore this email.
        </p>
      </body>
    </html>
    """
    _send_email(to_email, subject, body_plain, body_html)


def send_password_reset_email(to_email: str, otp: str) -> None:
    subject = f"Reset your {BREVO_SENDER_NAME} password"
    body_plain = (
        f"Your password reset code is: {otp}\n\n"
        "This code expires in 10 minutes.\n\n"
        "If you did not request a password reset, please ignore this email."
    )
    body_html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333;">
        <h2>Password Reset Request</h2>
        <p>Use the code below to reset your password:</p>
        <p style="font-size: 2em; font-weight: bold; letter-spacing: 4px;">{otp}</p>
        <p>This code expires in <strong>10 minutes</strong>.</p>
        <hr/>
        <p style="font-size: 0.85em; color: #888;">
          If you did not request a password reset, please ignore this email.
        </p>
      </body>
    </html>
    """
    _send_email(to_email, subject, body_plain, body_html)