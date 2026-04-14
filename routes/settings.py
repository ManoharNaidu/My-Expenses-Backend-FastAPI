import logging
import datetime as dt
from fastapi import APIRouter, HTTPException, Depends

from core.database import supabase
from core.config import WEEKLY_DIGEST_CRON_TOKEN
from core.email import send_weekly_digest_email
from core.security import verify_password, hash_password
from routes.auth import get_current_user
from schemas.settings import (
    AppLockUpdateRequest,
    UpdateNameRequest,
    UpdatePasswordRequest,
    UpdateCategoriesRequest,
    UpdateCurrencyRequest,
    WeeklyDigestSettingsUpdateRequest,
    WeeklyDigestSettingsResponse,
)
from services.weekly_digest import (
    build_weekly_digest_email,
    build_weekly_digest_summary,
    should_send_weekly_digest_now,
)

router = APIRouter(prefix="/settings")
logger = logging.getLogger(__name__)


def _normalize_weekly_digest_row(row: dict | None) -> dict:
    base = {
        "enabled": True,
        "weekday": 0,
        "hour": 18,
        "minute": 0,
        "timezone": "UTC",
        "last_sent_week": None,
    }
    if not row:
        return base
    for key in base:
        if key in row and row[key] is not None:
            base[key] = row[key]
    return base


def _upsert_weekly_digest_settings(user_id: str, payload: dict) -> dict:
    existing = (
        supabase.table("weekly_digest_settings")
        .select("id")
        .eq("user_id", user_id)
        .execute()
        .data
    )

    if existing:
        updated = (
            supabase.table("weekly_digest_settings")
            .update(payload)
            .eq("user_id", user_id)
            .execute()
            .data
        )
        return (updated or [payload])[0]

    inserted = (
        supabase.table("weekly_digest_settings")
        .insert({"user_id": user_id, **payload})
        .execute()
        .data
    )
    return (inserted or [{"user_id": user_id, **payload}])[0]


def _raise_feature_unavailable(feature: str, exc: Exception) -> None:
    logger.exception("%s unavailable: %s", feature, exc)
    raise HTTPException(
        status_code=503,
        detail=f"{feature} is not available yet. Please run latest database migrations.",
    )


@router.put("/name")
def update_name(data: UpdateNameRequest, user=Depends(get_current_user)):
    supabase.from_("users") \
        .update({"name": data.name}) \
        .eq("id", user["id"]) \
        .execute()

    return {"message": "Name updated"}


@router.put("/password")
def update_password(data: UpdatePasswordRequest, user=Depends(get_current_user)):
    if not verify_password(data.current_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    supabase.from_("users") \
        .update({"password_hash": hash_password(data.new_password)}) \
        .eq("id", user["id"]) \
        .execute()

    return {"message": "Password updated"}


@router.put("/currency")
def update_currency(data: UpdateCurrencyRequest, user=Depends(get_current_user)):
    supabase.from_("users") \
        .update({"currency": data.currency.upper()}) \
        .eq("id", user["id"]) \
        .execute()

    return {"message": "Currency updated", "currency": data.currency.upper()}


@router.put("/categories")
def update_categories(data: UpdateCategoriesRequest, user=Depends(get_current_user)):
    # Delete existing categories
    supabase.table("user_categories") \
        .delete() \
        .eq("user_id", user["id"]) \
        .execute()
    


    # Insert new categories
    category_records = []

    for pair in data.categories:
        if pair.get("income_category"):
            category_records.append({
                "user_id": user["id"],
                "type": "income",
                "category": pair.get("income_category")
            })

        if pair.get("expense_category"):
            category_records.append({
                "user_id": user["id"],
                "type": "expense",
                "category": pair.get("expense_category")
            })

    if category_records:
        supabase.table("user_categories").insert(category_records).execute()

    return {"message": "Categories updated", "categories": data.categories}


@router.get("/app-lock")
def get_app_lock(user=Depends(get_current_user)):
    def _fallback_from_users_table():
        try:
            user_row = (
                supabase.table("users")
                .select("app_lock_enabled", "use_biometric", "pin_hash")
                .eq("id", user["id"])
                .single()
                .execute()
                .data
            )
        except Exception as exc:
            _raise_feature_unavailable("App lock", exc)

        if not user_row:
            return {"enabled": False, "use_biometric": False, "pin_hash": None}

        return {
            "enabled": bool(user_row.get("app_lock_enabled", False)),
            "use_biometric": bool(user_row.get("use_biometric", False)),
            "pin_hash": user_row.get("pin_hash"),
        }

    try:
        row = (
            supabase.table("app_locks")
            .select("enabled", "use_biometric", "pin_hash")
            .eq("user_id", user["id"])
            .single()
            .execute()
            .data
        )
    except Exception as exc:
        logger.warning("app_locks table unavailable, falling back to users columns: %s", exc)
        return _fallback_from_users_table()

    if not row:
        return _fallback_from_users_table()

    return {
        "enabled": bool(row.get("enabled", False)),
        "use_biometric": bool(row.get("use_biometric", False)),
        "pin_hash": row.get("pin_hash"),
    }


@router.put("/app-lock")
def update_app_lock(data: AppLockUpdateRequest, user=Depends(get_current_user)):
    payload = {
        "user_id": user["id"],
        "enabled": data.enabled,
        "use_biometric": data.use_biometric,
        "pin_hash": data.pin_hash,
    }

    try:
        existing = (
            supabase.table("app_locks")
            .select("id")
            .eq("user_id", user["id"])
            .single()
            .execute()
            .data
        )
    except Exception:
        existing = None

    try:
        if existing:
            updated = (
                supabase.table("app_locks")
                .update(
                    {
                        "enabled": data.enabled,
                        "use_biometric": data.use_biometric,
                        "pin_hash": data.pin_hash,
                    }
                )
                .eq("user_id", user["id"])
                .execute()
            )
            row = updated.data[0] if updated.data else payload
        else:
            inserted = supabase.table("app_locks").insert(payload).execute()
            row = inserted.data[0] if inserted.data else payload
    except Exception as exc:
        logger.warning("app_locks table unavailable, falling back to users columns: %s", exc)
        try:
            updated_user = (
                supabase.table("users")
                .update(
                    {
                        "app_lock_enabled": data.enabled,
                        "use_biometric": data.use_biometric,
                        "pin_hash": data.pin_hash,
                    }
                )
                .eq("id", user["id"])
                .execute()
            )
            user_row = updated_user.data[0] if updated_user.data else {}
            row = {
                "enabled": bool(user_row.get("app_lock_enabled", data.enabled)),
                "use_biometric": bool(user_row.get("use_biometric", data.use_biometric)),
                "pin_hash": user_row.get("pin_hash", data.pin_hash),
            }
        except Exception as fallback_exc:
            _raise_feature_unavailable("App lock", fallback_exc)

    return {
        "message": "App lock settings updated",
        "app_lock": {
            "enabled": bool(row.get("enabled", False)),
            "use_biometric": bool(row.get("use_biometric", False)),
            "pin_hash": row.get("pin_hash"),
        },
    }


@router.get("/weekly-digest", response_model=WeeklyDigestSettingsResponse)
def get_weekly_digest_settings(user=Depends(get_current_user)):
    try:
        row = (
            supabase.table("weekly_digest_settings")
            .select("enabled", "weekday", "hour", "minute", "timezone", "last_sent_week")
            .eq("user_id", user["id"])
            .single()
            .execute()
            .data
        )
    except Exception:
        row = None

    return _normalize_weekly_digest_row(row)


@router.put("/weekly-digest", response_model=WeeklyDigestSettingsResponse)
def update_weekly_digest_settings(
    data: WeeklyDigestSettingsUpdateRequest,
    user=Depends(get_current_user),
):
    payload = {
        "enabled": data.enabled,
        "weekday": data.weekday,
        "hour": data.hour,
        "minute": data.minute,
        "timezone": data.timezone,
    }
    try:
        row = _upsert_weekly_digest_settings(user["id"], payload)
    except Exception as exc:
        _raise_feature_unavailable("Weekly digest", exc)
    return _normalize_weekly_digest_row(row)


@router.get("/weekly-digest/preview")
def preview_weekly_digest(user=Depends(get_current_user)):
    summary = build_weekly_digest_summary(user["id"])
    email = build_weekly_digest_email(user.get("name"), user.get("currency"), summary)
    return {
        "summary": {
            "week_start": summary.week_start.isoformat(),
            "week_end": summary.week_end.isoformat(),
            "income_total": summary.income_total,
            "expense_total": summary.expense_total,
            "net_total": summary.net_total,
            "transaction_count": summary.transaction_count,
            "top_categories": summary.top_categories,
            "daily_expenses": summary.daily_expenses,
            "highest_expense": summary.highest_expense,
            "insight": summary.insight,
        },
        "email": email,
    }


@router.post("/weekly-digest/send-now")
def send_weekly_digest_now(user=Depends(get_current_user)):
    if not user.get("email"):
        raise HTTPException(status_code=400, detail="User email is missing")

    summary = build_weekly_digest_summary(user["id"])
    email = build_weekly_digest_email(user.get("name"), user.get("currency"), summary)

    send_weekly_digest_email(
        to_email=user["email"],
        subject=email["subject"],
        body_plain=email["plain"],
        body_html=email["html"],
    )

    return {
        "message": "Weekly digest sent",
        "to": user["email"],
        "subject": email["subject"],
    }


@router.post("/weekly-digest/dispatch")
def dispatch_weekly_digests(cron_token: str):
    if not WEEKLY_DIGEST_CRON_TOKEN:
        raise HTTPException(status_code=503, detail="Weekly digest dispatch token is not configured")
    if cron_token != WEEKLY_DIGEST_CRON_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid cron token")

    try:
        rows = (
            supabase.table("weekly_digest_settings")
            .select("user_id", "enabled", "weekday", "hour", "minute", "timezone", "last_sent_week")
            .eq("enabled", True)
            .execute()
            .data
        ) or []
    except Exception as exc:
        _raise_feature_unavailable("Weekly digest dispatch", exc)

    sent = 0
    skipped = 0
    failed = 0
    now = dt.datetime.now(dt.timezone.utc)

    for setting in rows:
        should_send, week_key = should_send_weekly_digest_now(setting, now)
        if not should_send:
            skipped += 1
            continue

        user_row = (
            supabase.table("users")
            .select("id", "name", "email", "currency")
            .eq("id", setting["user_id"])
            .single()
            .execute()
            .data
        )
        if not user_row or not user_row.get("email"):
            skipped += 1
            continue

        try:
            summary = build_weekly_digest_summary(setting["user_id"])
            email = build_weekly_digest_email(user_row.get("name"), user_row.get("currency"), summary)
            send_weekly_digest_email(
                to_email=user_row["email"],
                subject=email["subject"],
                body_plain=email["plain"],
                body_html=email["html"],
            )
            _upsert_weekly_digest_settings(setting["user_id"], {"last_sent_week": week_key})
            sent += 1
        except Exception:
            logger.exception("Failed to send weekly digest for user_id=%s", setting["user_id"])
            failed += 1

    return {
        "message": "Weekly digest dispatch finished",
        "sent": sent,
        "skipped": skipped,
        "failed": failed,
    }





