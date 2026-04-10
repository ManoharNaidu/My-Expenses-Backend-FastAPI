import logging
import threading
from typing import Callable, Optional
from uuid import uuid4

import jwt
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from slowapi import Limiter
from slowapi.util import get_remote_address

from core.config import JWT_ALGORITHM, JWT_SECRET
from core.database import supabase
from core.email import send_password_reset_email, send_verification_email
from core.otp import check_resend_rate_limit, consume_otp, generate_otp, insert_otp
from core.security import create_access_token, decode_access_token, hash_password, verify_password
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth")
security = HTTPBearer(auto_error=False)
limiter = Limiter(key_func=get_remote_address)


# ── helpers ───────────────────────────────────────────────────────────────────

def _set_session_cookie(response: Response, token: str):
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        secure=True,  # Mandatory for cross-site (Flutter web, etc.)
        samesite="none",  # Required for cross-site cookies
        max_age=60 * 60 * 24 * 365,  # 1 year
        path="/",
    )


def _clear_session_cookie(response: Response):
    response.delete_cookie(
        key="session",
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
    )


def _fire_and_forget(fn: Callable, *args) -> None:
    """Run fn(*args) in a daemon thread — never blocks the response."""
    threading.Thread(target=fn, args=args, daemon=True).start()


def _get_user_by_email(email: str) -> Optional[dict]:
    """Return the user row or None. Uses limit(1) instead of .single() + bare except."""
    rows = (
        supabase.from_("users")
        .select("*")
        .eq("email", email)
        .limit(1)
        .execute()
        .data
    )
    return rows[0] if rows else None


def _get_user_by_id(user_id: str) -> Optional[dict]:
    rows = (
        supabase.from_("users")
        .select("*")
        .eq("id", user_id)
        .limit(1)
        .execute()
        .data
    )
    return rows[0] if rows else None


# ── routes ────────────────────────────────────────────────────────────────────

@router.post("/register", response_model=MessageResponse)
@limiter.limit("10/minute")
def register(request: Request, data: RegisterRequest, bg: BackgroundTasks):
    user = _get_user_by_email(data.email)

    if user:
        if user.get("is_verified"):
            raise HTTPException(status_code=400, detail="Email already registered")

        # Unverified re-registration: refresh details and resend OTP
        supabase.from_("users").update(
            {
                "name": data.name,
                "password_hash": hash_password(data.password),
                "currency": (data.currency or "AUD").upper(),
            }
        ).eq("id", user["id"]).execute()

        otp = generate_otp()
        insert_otp("email_verification", user["id"], otp)
        bg.add_task(send_verification_email, data.email, otp)
        return {"message": "Registration successful. Please check your email for the verification code."}

    user_id = str(uuid4())
    supabase.from_("users").insert(
        {
            "id": user_id,
            "name": data.name,
            "email": data.email,
            "password_hash": hash_password(data.password),
            "is_onboarded": False,
            "is_verified": False,
            "currency": (data.currency or "AUD").upper(),
            "token_version": 0,
        }
    ).execute()

    otp = generate_otp()
    insert_otp("email_verification", user_id, otp)
    bg.add_task(send_verification_email, data.email, otp)
    return {"message": "Registration successful. Please check your email for the verification code."}


@router.post("/login", response_model=AuthResponse)
@limiter.limit("10/month")
def login(request: Request, data: LoginRequest, bg: BackgroundTasks):
    user = _get_user_by_email(data.email)

    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.get("is_verified"):
        # Send a fresh OTP so the user can still verify
        otp = generate_otp()
        insert_otp("email_verification", user["id"], otp)
        bg.add_task(send_verification_email, user["email"], otp)
        return JSONResponse(
            status_code=403,
            content={
                "message": "Email not verified. A new verification code has been sent to your email.",
                "requires_verification": True,
            },
        )

    token = create_access_token(
        {"sub": user["id"], "ver": user.get("token_version", 0)}
    )
    
    response = JSONResponse(content={"access_token": token})
    _set_session_cookie(response, token)
    return response


@router.post("/logout", response_model=MessageResponse)
def logout(response: Response):
    _clear_session_cookie(response)
    return {"message": "Logged out successfully"}


@router.post("/verify-email", response_model=AuthResponse)
@limiter.limit("10/minute")
def verify_email(request: Request, data: VerifyEmailRequest):
    user = _get_user_by_email(data.email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.get("is_verified"):
        raise HTTPException(status_code=400, detail="Email is already verified")

    consume_otp("email_verification", user["id"], data.otp)

    supabase.table("users").update({"is_verified": True}).eq("id", user["id"]).execute()

    token = create_access_token(
        {"sub": user["id"], "ver": user.get("token_version", 0)}
    )
    
    response = JSONResponse(content={"access_token": token})
    _set_session_cookie(response, token)
    return response


@router.post("/resend-verification", response_model=MessageResponse)
@limiter.limit("5/minute")
def resend_verification(request: Request, data: ResendVerificationRequest, bg: BackgroundTasks):
    user = _get_user_by_email(data.email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.get("is_verified"):
        raise HTTPException(status_code=400, detail="Email is already verified")

    check_resend_rate_limit(user["id"], "email_verification")

    otp = generate_otp()
    insert_otp("email_verification", user["id"], otp)
    bg.add_task(send_verification_email, data.email, otp)
    return {"message": "Verification code sent. Please check your email."}


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("5/minute")
def forgot_password(request: Request, data: ForgotPasswordRequest, bg: BackgroundTasks):
    user = _get_user_by_email(data.email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    check_resend_rate_limit(user["id"], "password_reset")

    otp = generate_otp()
    insert_otp("password_reset", user["id"], otp)
    bg.add_task(send_password_reset_email, data.email, otp)
    return {"message": "Password reset code sent. Please check your email."}


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit("5/minute")
def reset_password(request: Request, data: ResetPasswordRequest):
    user = _get_user_by_email(data.email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    consume_otp("password_reset", user["id"], data.otp)

    # Bump token_version — invalidates all previously issued JWTs for this user
    supabase.table("users").update(
        {
            "password_hash": hash_password(data.new_password),
            "token_version": (user.get("token_version") or 0) + 1,
        }
    ).eq("id", user["id"]).execute()

    return {"message": "Password reset successful. You can now log in with your new password."}


# ── auth dependency ───────────────────────────────────────────────────────────

def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    token = None
    if credentials:
        token = credentials.credentials
    else:
        token = request.cookies.get("session")

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = _get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # Reject tokens issued before a password reset
    token_ver = payload.get("ver", 0)
    if token_ver != user.get("token_version", 0):
        raise HTTPException(status_code=401, detail="Token has been revoked")

    return user


@router.get("/me")
def me(user=Depends(get_current_user)):
    response = {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "is_onboarded": user["is_onboarded"],
        "currency": user.get("currency"),
        "persona": user.get("persona"),
    }

    if user["is_onboarded"]:
        rows = (
            supabase.table("user_categories")
            .select("type", "category")
            .eq("user_id", user["id"])
            .execute()
            .data
        )
        response["categories"] = {
            "income_categories": [r["category"] for r in rows if r["type"] == "income"],
            "expense_categories": [r["category"] for r in rows if r["type"] == "expense"],
        }

    app_lock_rows = (
        supabase.table("app_locks")
        .select("enabled", "use_biometric", "pin_hash")
        .eq("user_id", user["id"])
        .limit(1)
        .execute()
        .data
    )
    app_lock = app_lock_rows[0] if app_lock_rows else None

    response["app_lock"] = {
        "enabled": bool(app_lock.get("enabled", False)) if app_lock else False,
        "use_biometric": bool(app_lock.get("use_biometric", False)) if app_lock else False,
        "pin_hash": app_lock.get("pin_hash") if app_lock else None,
    }

    return response
