import logging
from fastapi import APIRouter, HTTPException, Depends

from core.database import supabase
from core.security import verify_password, hash_password
from routes.auth import get_current_user
from schemas.settings import (
    AppLockUpdateRequest,
    UpdateNameRequest,
    UpdatePasswordRequest,
    UpdateCategoriesRequest,
    UpdateCurrencyRequest,
)

router = APIRouter(prefix="/settings")
logger = logging.getLogger(__name__)


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
        logger.warning("App lock table may be unavailable: %s", exc)
        row = None

    if not row:
        return {"enabled": False, "use_biometric": False, "pin_hash": None}
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
        _raise_feature_unavailable("App lock", exc)

    return {
        "message": "App lock settings updated",
        "app_lock": {
            "enabled": bool(row.get("enabled", False)),
            "use_biometric": bool(row.get("use_biometric", False)),
            "pin_hash": row.get("pin_hash"),
        },
    }




