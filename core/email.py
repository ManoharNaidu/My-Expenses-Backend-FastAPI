import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from core.config import (
    BREVO_SENDER_EMAIL,
    BREVO_SENDER_NAME,
    BREVO_SMTP_HOST,
    BREVO_SMTP_PASSWORD,
    BREVO_SMTP_PORT,
    BREVO_SMTP_USER,
)

logger = logging.getLogger(__name__)


def _send_email(to_email: str, subject: str, body: str) -> None:
    """Send a plain-text email via Brevo SMTP (STARTTLS on port 587)."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{BREVO_SENDER_NAME} <{BREVO_SENDER_EMAIL}>"
    msg["To"] = to_email
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(BREVO_SMTP_HOST, BREVO_SMTP_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(BREVO_SMTP_USER, BREVO_SMTP_PASSWORD)
            server.sendmail(BREVO_SENDER_EMAIL, to_email, msg.as_string())
    except Exception:
        logger.exception("Failed to send email to %s", to_email)
        raise


def send_verification_email(to_email: str, otp: str) -> None:
    subject = "Verify your Expense Tracker account"
    body = (
        f"Your verification code is: {otp}\n\n"
        "This code will expire in 10 minutes."
    )
    _send_email(to_email, subject, body)


def send_password_reset_email(to_email: str, otp: str) -> None:
    subject = "Password Reset OTP"
    body = (
        f"Your password reset code is: {otp}\n\n"
        "This code expires in 10 minutes."
    )
    _send_email(to_email, subject, body)

