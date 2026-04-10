import logging
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from postgrest.exceptions import APIError

from core.database import supabase
from core.ml_classifier import ml_service
from models.transactions import (
    BudgetGoalUpdate,
    RecurringTransactionCreate,
    RecurringTransactionToggle,
    TransactionConfirm,
    TransactionCreate,
)
from routes.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

_LIMIT_MIN = 1
_LIMIT_MAX = 100
_OFFSET_MIN = 0


def _normalize_type(raw: str) -> str:
    value = (raw or "").strip().lower()
    if value in {"income", "credit"}:
        return "income"
    return "expense"


def _normalize_description(*values: str | None) -> str:
    for value in values:
        text = (value or "").strip()
        if text:
            return text
    return ""


def _raise_feature_unavailable(feature: str, exc: Exception) -> None:
    logger.exception("%s unavailable: %s", feature, exc)
    raise HTTPException(
        status_code=503,
        detail=f"{feature} is not available yet. Please run latest database migrations.",
    )


@router.get("/transactions")
def get_user_transactions(
    user=Depends(get_current_user),
    limit: int = 10,
    offset: int = 0,
):
    limit = max(_LIMIT_MIN, min(_LIMIT_MAX, limit))
    offset = max(_OFFSET_MIN, offset)
    return (
        supabase.table("transactions")
        .select("*")
        .eq("user_id", user["id"])
        .order("date", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
        .data
    )


@router.get("/categories")
def get_categories(user=Depends(get_current_user)):
    rows = (
        supabase.table("user_categories")
        .select("type", "category")
        .eq("user_id", user["id"])
        .execute()
        .data
    )
    income = [r["category"] for r in rows if (r.get("type") or "").lower() == "income"]
    expense = [r["category"] for r in rows if (r.get("type") or "").lower() == "expense"]
    return {
        "income_categories": income,
        "expense_categories": expense,
        "all_categories": sorted({*income, *expense}),
    }


@router.delete("/transactions/{transaction_id}")
def delete_transaction(transaction_id: str, user=Depends(get_current_user)):
    supabase.table("transactions").delete().eq("id", transaction_id).eq("user_id", user["id"]).execute()
    return {"message": "Transaction deleted"}


@router.post("/transactions")
def create_transaction(data: TransactionCreate, bg: BackgroundTasks, user=Depends(get_current_user)):
    tx_type = _normalize_type(data.type)
    description = _normalize_description(data.notes, data.description)

    record = {
        "user_id": user["id"],
        "date": data.date.isoformat(),
        "description": description,
        "amount": data.amount,
        "type": tx_type,
        "category": data.category,
    }
    try:
        result = supabase.table("transactions").insert(record).execute()
    except APIError as exc:
        if isinstance(exc.args[0], dict) and exc.args[0].get("code") == "23502":
            raise HTTPException(status_code=422, detail="Description is required") from exc
        raise

    recurring_warning = None
    if data.repeat_monthly:
        try:
            start = data.date.date()
            supabase.table("recurring_transactions").insert(
                {
                    "user_id": user["id"],
                    "amount": data.amount,
                    "type": tx_type,
                    "category": data.category,
                    "description": description,
                    "start_date": start.isoformat(),
                    "day_of_month": min(start.day, 28),
                    "is_active": True,
                }
            ).execute()
        except Exception as exc:
            logger.warning("Recurring template could not be created for user %s: %s", user["id"], exc)
            recurring_warning = "Recurring template was not created. Please run latest database migrations."

    # Retrain ML model in background — does not block the response
    bg.add_task(ml_service.refresh_user_model, user["id"])

    created = result.data[0] if result.data else None
    return {
        "message": "Transaction added",
        "transaction": created,
        "id": created.get("id") if created else None,
        "warning": recurring_warning,
    }


@router.put("/transactions/{transaction_id}")
def update_transaction(transaction_id: str, data: TransactionCreate, bg: BackgroundTasks, user=Depends(get_current_user)):
    tx_type = _normalize_type(data.type)
    description = _normalize_description(data.notes, data.description)

    record = {
        "date": data.date.isoformat(),
        "description": description,
        "amount": data.amount,
        "type": tx_type,
        "category": data.category,
    }
    result = (
        supabase.table("transactions")
        .update(record)
        .eq("id", transaction_id)
        .eq("user_id", user["id"])
        .execute()
    )

    bg.add_task(ml_service.refresh_user_model, user["id"])
    return {"message": "Transaction updated", "transaction": result.data[0] if result.data else None}


@router.get("/recurring-transactions")
def list_recurring_transactions(user=Depends(get_current_user)):
    try:
        rows = (
            supabase.table("recurring_transactions")
            .select("*")
            .eq("user_id", user["id"])
            .order("created_at", desc=True)
            .execute()
            .data
        )
    except Exception as exc:
        _raise_feature_unavailable("Recurring transactions", exc)
    return rows


@router.post("/recurring-transactions")
def create_recurring_transaction(data: RecurringTransactionCreate, user=Depends(get_current_user)):
    tx_type = _normalize_type(data.type)
    record = {
        "user_id": user["id"],
        "amount": data.amount,
        "type": tx_type,
        "category": data.category,
        "description": _normalize_description(data.description),
        "start_date": data.start_date.date().isoformat(),
        "day_of_month": data.day_of_month,
        "end_date": data.end_date.date().isoformat() if data.end_date else None,
        "is_active": data.is_active,
    }
    try:
        result = supabase.table("recurring_transactions").insert(record).execute()
    except Exception as exc:
        _raise_feature_unavailable("Recurring transactions", exc)
    return {"message": "Recurring transaction created", "recurring": result.data[0] if result.data else None}


@router.put("/recurring-transactions/{recurring_id}")
def toggle_recurring_transaction(
    recurring_id: str,
    data: RecurringTransactionToggle,
    user=Depends(get_current_user),
):
    try:
        result = (
            supabase.table("recurring_transactions")
            .update({"is_active": data.is_active})
            .eq("id", recurring_id)
            .eq("user_id", user["id"])
            .execute()
        )
    except Exception as exc:
        _raise_feature_unavailable("Recurring transactions", exc)
    return {"message": "Recurring transaction updated", "recurring": result.data[0] if result.data else None}


@router.post("/recurring-transactions/{recurring_id}/duplicate-now")
def duplicate_recurring_now(recurring_id: str, user=Depends(get_current_user)):
    try:
        recurring_rows = (
            supabase.table("recurring_transactions")
            .select("*")
            .eq("id", recurring_id)
            .eq("user_id", user["id"])
            .limit(1)
            .execute()
            .data
        )
    except Exception as exc:
        _raise_feature_unavailable("Recurring transactions", exc)

    if not recurring_rows:
        raise HTTPException(status_code=404, detail="Recurring transaction not found")

    recurring = recurring_rows[0]
    today = date.today().isoformat()
    created = supabase.table("transactions").insert(
        {
            "user_id": user["id"],
            "date": today,
            "description": _normalize_description(recurring.get("description")),
            "amount": recurring.get("amount"),
            "type": recurring.get("type"),
            "category": recurring.get("category"),
        }
    ).execute()
    return {"message": "Transaction duplicated", "transaction": created.data[0] if created.data else None}


@router.get("/budget-goal")
def get_budget_goal(user=Depends(get_current_user)):
    rows = (
        supabase.table("budget_goals")
        .select("*")
        .eq("user_id", user["id"])
        .limit(1)
        .execute()
        .data
    )
    return rows[0] if rows else {"monthly_limit": 0, "alerts_enabled": True}


@router.put("/budget-goal")
def update_budget_goal(data: BudgetGoalUpdate, user=Depends(get_current_user)):
    payload = {
        "user_id": user["id"],
        "monthly_limit": data.monthly_limit,
        "alerts_enabled": data.alerts_enabled,
    }
    existing_rows = (
        supabase.table("budget_goals")
        .select("id")
        .eq("user_id", user["id"])
        .limit(1)
        .execute()
        .data
    )
    try:
        if existing_rows:
            updated = (
                supabase.table("budget_goals")
                .update({"monthly_limit": data.monthly_limit, "alerts_enabled": data.alerts_enabled})
                .eq("user_id", user["id"])
                .execute()
            )
            record = updated.data[0] if updated.data else payload
        else:
            inserted = supabase.table("budget_goals").insert(payload).execute()
            record = inserted.data[0] if inserted.data else payload
    except Exception as exc:
        _raise_feature_unavailable("Budget goals", exc)

    return {"message": "Budget goal updated", "budget_goal": record}


@router.get("/budget-goal/progress")
def budget_progress(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    user=Depends(get_current_user),
):
    goal = get_budget_goal(user)
    monthly_limit = float(goal.get("monthly_limit") or 0)

    start = f"{year}-{str(month).zfill(2)}-01"
    end = f"{year}-{str(month).zfill(2)}-31"
    txs = (
        supabase.table("transactions")
        .select("amount", "type", "date")
        .eq("user_id", user["id"])
        .gte("date", start)
        .lte("date", end)
        .execute()
        .data
    )

    total_expense = sum(
        float(tx.get("amount") or 0)
        for tx in txs
        if _normalize_type(tx.get("type")) == "expense"
    )

    progress = (total_expense / monthly_limit) if monthly_limit > 0 else 0.0
    return {
        "year": year,
        "month": month,
        "monthly_limit": monthly_limit,
        "expense_spent": round(total_expense, 2),
        "progress": round(progress, 4),
        "alerts_enabled": bool(goal.get("alerts_enabled", True)),
        "is_over_budget": monthly_limit > 0 and total_expense > monthly_limit,
    }


@router.get("/staging")
def get_staging_transactions(user=Depends(get_current_user)):
    return (
        supabase.table("transactions_staging")
        .select("*")
        .eq("user_id", user["id"])
        .eq("is_confirmed", False)
        .order("date", desc=True)
        .execute()
        .data
    )


@router.post("/confirm-staging-transactions")
def confirm_transactions(payload: list[TransactionConfirm], bg: BackgroundTasks, user=Depends(get_current_user)):
    if not payload:
        raise HTTPException(status_code=400, detail="No transactions provided")

    ids = [txn.id for txn in payload if txn.id]
    if not ids:
        raise HTTPException(status_code=400, detail="No valid transaction IDs provided")

    # Single batch fetch — eliminates N+1
    staging_rows = (
        supabase.table("transactions_staging")
        .select("*")
        .in_("id", ids)
        .eq("user_id", user["id"])
        .execute()
        .data
    )
    staging_by_id = {row["id"]: row for row in staging_rows}

    # Build batches
    transactions_to_insert = []
    feedback_to_insert = []
    confirmed_ids = []

    for txn in payload:
        row = staging_by_id.get(txn.id)
        if not row:
            continue

        transactions_to_insert.append(
            {
                "user_id": user["id"],
                "date": row["date"],
                "description": _normalize_description(row.get("description")),
                "amount": row["amount"],
                "type": _normalize_type(txn.final_type),
                "category": txn.final_category,
            }
        )
        feedback_to_insert.append(
            {
                "user_id": user["id"],
                "description": row.get("description"),
                "predicted_type": row.get("predicted_type"),
                "predicted_category": row.get("predicted_category"),
                "corrected_type": _normalize_type(txn.final_type),
                "corrected_category": txn.final_category,
            }
        )
        confirmed_ids.append(txn.id)

    if not confirmed_ids:
        raise HTTPException(status_code=400, detail="No valid staging transactions were confirmed")

    # Batch inserts
    supabase.table("transactions").insert(transactions_to_insert).execute()
    supabase.table("ml_feedback").insert(feedback_to_insert).execute()

    # Batch update staging rows
    supabase.table("transactions_staging").update({"is_confirmed": True}).in_("id", confirmed_ids).execute()

    bg.add_task(ml_service.refresh_user_model, user["id"])
    return {"status": "confirmed", "count": len(confirmed_ids)}
