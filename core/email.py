import logging
import time
from typing import Optional

import requests

from core.config import BREVO_API_KEY, BREVO_SENDER_EMAIL, BREVO_SENDER_NAME

logger = logging.getLogger(__name__)

_API_RETRIES = 3
_API_RETRY_DELAY = 2  # seconds
_API_RETRY_STATUSES = {429, 500, 502, 503, 504}
_BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


def _send_email(
    to_email: str,
    subject: str,
    body_plain: str,
    body_html: Optional[str] = None,
) -> None:
    """Send an email via Brevo v3 Transactional Email API.

    Retries on transient Brevo errors (429/5xx) with small back-off.
    """
    payload = {
        "sender": {"name": BREVO_SENDER_NAME, "email": BREVO_SENDER_EMAIL},
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": body_plain,
    }
    if body_html:
        payload["htmlContent"] = body_html

    headers = {
        "api-key": BREVO_API_KEY,
        "accept": "application/json",
        "content-type": "application/json",
    }

    last_exc: Optional[Exception] = None
    for attempt in range(1, _API_RETRIES + 1):
        try:
            resp = requests.post(_BREVO_ENDPOINT, json=payload, headers=headers, timeout=10)
            if resp.status_code < 300:
                logger.info("Email sent to %s (attempt %d)", to_email, attempt)
                return

            if resp.status_code in _API_RETRY_STATUSES:
                logger.warning(
                    "Brevo API retryable error (%s) for %s: %s",
                    resp.status_code,
                    to_email,
                    resp.text,
                )
                last_exc = Exception(f"Brevo API {resp.status_code}: {resp.text}")
            else:
                # Non-retryable HTTP error
                resp.raise_for_status()
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Failed to send email to %s on attempt %d/%d: %s",
                to_email,
                attempt,
                _API_RETRIES,
                exc,
            )

        if attempt < _API_RETRIES:
            time.sleep(_API_RETRY_DELAY)

    logger.error("All %d Brevo API attempts failed for %s", _API_RETRIES, to_email)
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
