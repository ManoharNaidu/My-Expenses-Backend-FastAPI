import random
import string
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from core.config import JWT_ALGORITHM, JWT_SECRET
from core.database import supabase
from core.email import send_password_reset_email, send_verification_email
from core.security import create_access_token, hash_password, verify_password
from schemas.auth import (
    AuthResponse,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
)

router = APIRouter(prefix="/auth")
security = HTTPBearer()

_OTP_EXPIRE_MINUTES = 10
_OTP_MAX_RESENDS_PER_HOUR = 5


# ── helpers ───────────────────────────────────────────────────────────────────

def _generate_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


def _otp_expires_at() -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=_OTP_EXPIRE_MINUTES)).isoformat()


def _check_resend_rate_limit(user_id: str, table: str) -> None:
    """Raise 429 if the user has already sent ≥5 OTPs in the last hour."""
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    result = (
        supabase.table(table)
        .select("id", count="exact")
        .eq("user_id", user_id)
        .gte("created_at", one_hour_ago)
        .execute()
    )
    if (result.count or 0) >= _OTP_MAX_RESENDS_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait before requesting another code.",
        )


def _insert_otp(table: str, user_id: str, otp: str) -> None:
    supabase.table(table).insert({
        "id": str(uuid4()),
        "user_id": user_id,
        "otp": otp,
        "expires_at": _otp_expires_at(),
        "used": False,
    }).execute()


def _consume_otp(table: str, user_id: str, otp: str) -> None:
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


# ── routes ────────────────────────────────────────────────────────────────────

@router.post("/register", response_model=MessageResponse)
def register(data: RegisterRequest):
    existing = supabase.from_("users").select("id").eq("email", data.email).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="Email already registered")

    user_id = str(uuid4())
    supabase.from_("users").insert({
        "id": user_id,
        "name": data.name,
        "email": data.email,
        "password_hash": hash_password(data.password),
        "is_onboarded": False,
        "is_verified": False,
        "currency": (data.currency or "AUD").upper(),
    }).execute()

    otp = _generate_otp()
    _insert_otp("email_verification", user_id, otp)
    send_verification_email(data.email, otp)

    return {"message": "Registration successful. Please check your email for the verification code."}


@router.post("/login", response_model=AuthResponse)
def login(data: LoginRequest):
    try:
        res = supabase.from_("users").select("*").eq("email", data.email).single().execute()
        user = res.data
    except Exception:
        user = None

    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.get("is_verified"):
        # Send a fresh OTP so the user can still verify
        otp = _generate_otp()
        _insert_otp("email_verification", user["id"], otp)
        send_verification_email(user["email"], otp)
        raise HTTPException(
            status_code=403,
            detail="Email not verified. A new verification code has been sent to your email.",
        )

    token = create_access_token({"sub": user["id"]})
    return {"access_token": token}


@router.post("/verify-email", response_model=AuthResponse)
def verify_email(data: VerifyEmailRequest):
    try:
        res = supabase.from_("users").select("id, is_verified").eq("email", data.email).single().execute()
        user = res.data
    except Exception:
        user = None

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.get("is_verified"):
        raise HTTPException(status_code=400, detail="Email is already verified")

    _consume_otp("email_verification", user["id"], data.otp)

    supabase.table("users").update({"is_verified": True}).eq("id", user["id"]).execute()

    token = create_access_token({"sub": user["id"]})
    return {"access_token": token}


@router.post("/resend-verification", response_model=MessageResponse)
def resend_verification(data: ResendVerificationRequest):
    try:
        res = supabase.from_("users").select("id, is_verified").eq("email", data.email).single().execute()
        user = res.data
    except Exception:
        user = None

    # Always return success to avoid user enumeration
    if not user or user.get("is_verified"):
        return {"message": "If your email is registered and unverified, a code has been sent."}

    _check_resend_rate_limit(user["id"], "email_verification")

    otp = _generate_otp()
    _insert_otp("email_verification", user["id"], otp)
    send_verification_email(data.email, otp)

    return {"message": "Verification code sent. Please check your email."}


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(data: ForgotPasswordRequest):
    try:
        res = supabase.from_("users").select("id").eq("email", data.email).single().execute()
        user = res.data
    except Exception:
        user = None

    # Always return success to avoid user enumeration
    if not user:
        return {"message": "If that email is registered, a password reset code has been sent."}

    _check_resend_rate_limit(user["id"], "password_reset")

    otp = _generate_otp()
    _insert_otp("password_reset", user["id"], otp)
    send_password_reset_email(data.email, otp)

    return {"message": "Password reset code sent. Please check your email."}


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(data: ResetPasswordRequest):
    try:
        res = supabase.from_("users").select("id").eq("email", data.email).single().execute()
        user = res.data
    except Exception:
        user = None

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    _consume_otp("password_reset", user["id"], data.otp)

    supabase.table("users").update({
        "password_hash": hash_password(data.new_password)
    }).eq("id", user["id"]).execute()

    return {"message": "Password reset successful. You can now log in with your new password."}

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM]
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        try:
            user = supabase.from_("users").select("*").eq("id", user_id).single().execute().data
        except Exception:
            user = None

        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

@router.get("/me")
def me(user=Depends(get_current_user)):
    response = {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "is_onboarded": user["is_onboarded"],
        "currency": user.get("currency"),
    }

    if user["is_onboarded"]:
        rows = supabase.table("user_categories") \
            .select("type", "category") \
            .eq("user_id", user["id"]) \
            .execute().data
        response["categories"] = {
            "income_categories": [r["category"] for r in rows if r["type"] == "income"],
            "expense_categories": [r["category"] for r in rows if r["type"] == "expense"]
        }

    try:
        app_lock = (
            supabase.table("app_locks")
            .select("enabled", "use_biometric", "pin_hash")
            .eq("user_id", user["id"])
            .single()
            .execute()
            .data
        )
    except Exception:
        app_lock = None

    response["app_lock"] = {
        "enabled": bool(app_lock.get("enabled", False)) if app_lock else False,
        "use_biometric": bool(app_lock.get("use_biometric", False)) if app_lock else False,
        "pin_hash": app_lock.get("pin_hash") if app_lock else None,
    }

    return response
