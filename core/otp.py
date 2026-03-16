"""
Centralised OTP helpers.

OTPs are stored as SHA-256 hex digests so a database breach does not expose
live codes. The 10-minute expiry window is the primary security control;
SHA-256 without a salt is acceptable here because:
  - the OTP search space is 1 000 000 values
  - the window to exploit a stolen hash is only 10 minutes
  - rate limiting on consuming endpoints prevents online brute-force
"""

from __future__ import annotations

import hashlib
import logging
import random
import string
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException

from core.database import supabase

logger = logging.getLogger(__name__)

_OTP_EXPIRE_MINUTES = 10
_OTP_MAX_PER_HOUR = 5


def _hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


def generate_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


def _otp_expires_at() -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=_OTP_EXPIRE_MINUTES)).isoformat()


def check_resend_rate_limit(user_id: str, table: str) -> None:
    """Raise 429 if the user has already sent >=5 OTPs in the last hour."""
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    result = (
        supabase.table(table)
        .select("id", count="exact")
        .eq("user_id", user_id)
        .gte("created_at", one_hour_ago)
        .execute()
    )
    if (result.count or 0) >= _OTP_MAX_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait before requesting another code.",
        )


def insert_otp(table: str, user_id: str, otp: str) -> None:
    """Hash and persist the OTP."""
    supabase.table(table).insert(
        {
            "id": str(uuid4()),
            "user_id": user_id,
            "otp": _hash_otp(otp),
            "expires_at": _otp_expires_at(),
            "used": False,
        }
    ).execute()


def consume_otp(table: str, user_id: str, otp: str) -> None:
    """
    Validate a submitted OTP against its stored hash and mark it used.
    Raises HTTPException(400) if no matching valid OTP exists.
    """
    now = datetime.now(timezone.utc).isoformat()
    rows = (
        supabase.table(table)
        .select("id, expires_at, used")
        .eq("user_id", user_id)
        .eq("otp", _hash_otp(otp))
        .eq("used", False)
        .gte("expires_at", now)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")
    supabase.table(table).update({"used": True}).eq("id", rows[0]["id"]).execute()
