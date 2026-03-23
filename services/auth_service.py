import time
import string
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi import HTTPException
from core.database import supabase

_OTP_EXPIRE_MINUTES = 10
_OTP_MAX_RESENDS_PER_HOUR = 5
_RATE_LIMITS = {}

def generate_otp() -> str:
    return "".join(secrets.choice(string.digits) for _ in range(6))

def otp_expires_at() -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=_OTP_EXPIRE_MINUTES)).isoformat()

def check_resend_rate_limit(user_id: str, table: str) -> None:
    now = time.time()
    key = f"{user_id}:{table}"
    
    if key not in _RATE_LIMITS:
        _RATE_LIMITS[key] = []
        
    _RATE_LIMITS[key] = [t for t in _RATE_LIMITS[key] if now - t < 3600]
    
    if len(_RATE_LIMITS[key]) >= _OTP_MAX_RESENDS_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait before requesting another code.",
        )
        
    _RATE_LIMITS[key].append(now)

def insert_otp(table: str, user_id: str, otp: str) -> None:
    supabase.table(table).insert({
        "id": str(uuid4()),
        "user_id": user_id,
        "otp": otp,
        "expires_at": otp_expires_at(),
        "used": False,
    }).execute()

def consume_otp(table: str, user_id: str, otp: str) -> None:
    """Validate and mark an OTP as used. Raises HTTPException on failure."""
    now = datetime.now(timezone.utc).isoformat()
    rows = (
        supabase.table(table)
        .select("id, expires_at, used")
        .eq("user_id", user_id)
        .eq("otp", otp)
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
