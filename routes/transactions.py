from fastapi import APIRouter, Depends, HTTPException

from core.database import supabase
from core.ml_classifier import ml_service
from models.transactions import TransactionConfirm, TransactionCreate
from routes.auth import get_current_user

router = APIRouter()

_LIMIT_MIN = 1
_LIMIT_MAX = 100
_OFFSET_MIN = 0


_LIMIT_MIN = 1
_LIMIT_MAX = 100
_OFFSET_MIN = 0

@router.get("/transactions")
def get_user_transactions(
    user=Depends(get_current_user),
    limit: int = 10,
    offset: int = 0,
):
    limit = max(_LIMIT_MIN, min(_LIMIT_MAX, limit))
    offset = max(_OFFSET_MIN, offset)
    return supabase.table("transactions") \
        .select("*") \
        .eq("user_id", user["id"]) \
        .order("date", desc=True) \
        .range(offset, offset + limit - 1) \
        .execute().data

@router.get("/categories")
def get_categories(user=Depends(get_current_user)):
    res = supabase.table("user_categories") \
        .select("*") \
        .eq("user_id", user["id"]) \
        .execute().data
    
    return {
        "Categories": res
    }

@router.delete("/transactions/{transaction_id}")
def delete_transaction(transaction_id: str, user=Depends(get_current_user)):
    supabase.table("transactions") \
        .delete() \
        .eq("id", transaction_id) \
        .eq("user_id", user["id"]) \
        .execute()
    return {"message": "Transaction deleted"}

@router.post("/transactions")
def create_transaction(data: TransactionCreate, user=Depends(get_current_user)):
    
    record = {
        "user_id": user["id"],
        "date": data.date.isoformat(),
        "description": data.description,
        "amount": data.amount,
        "type": data.type,
        "category": data.category,
    }

    result = supabase.table("transactions").insert(record).execute()
    ml_service.refresh_user_model(user["id"])

    return {"message": "Transaction added", "transaction": result.data[0]}

@router.put("/transactions/{transaction_id}")
def update_transaction(transaction_id: str, data: TransactionCreate, user=Depends(get_current_user)):
    record = {
        "date": data.date.isoformat(),
        "description": data.description,
        "amount": data.amount,
        "type": data.type,
        "category": data.category,
    }

    result = supabase.table("transactions") \
        .update(record) \
        .eq("id", transaction_id) \
        .eq("user_id", user["id"]) \
        .execute()

    ml_service.refresh_user_model(user["id"])

    return {"message": "Transaction updated", "transaction": result.data[0]}

@router.get("/staging")
def get_staging_transactions(user=Depends(get_current_user)):
    """List unconfirmed staging transactions (e.g. after PDF upload)."""
    return supabase.table("transactions_staging") \
        .select("*") \
        .eq("user_id", user["id"]) \
        .eq("is_confirmed", False) \
        .order("date", desc=True) \
        .order("date", desc=True) \
        .execute().data


@router.post("/confirm-staging-transactions")
def confirm_transactions(payload: list[TransactionConfirm], user=Depends(get_current_user)):
    confirmed_count = 0

    for txn in payload:
        if not txn.id:
            continue

        # fetch staging (scoped to user)
        try:
            row = supabase.table("transactions_staging") \
                .select("*") \
                .eq("id", txn.id) \
                .eq("user_id", user["id"]) \
                .single() \
                .execute().data
        except Exception:
            row = None

        if not row:
            continue

        # insert final
        supabase.table("transactions").insert({
            "user_id": user["id"],
            "date": row["date"],
            "description": row["description"],
            "amount": row["amount"],
            "type": txn.final_type,
            "category": txn.final_category,
        }).execute()

        # ML feedback
        supabase.table("ml_feedback").insert({
            "user_id": user["id"],
            "description": row["description"],
            "predicted_type": row["predicted_type"],
            "predicted_category": row["predicted_category"],
            "corrected_type": txn.final_type,
            "corrected_category": txn.final_category,
        }).execute()

        # mark confirmed
        supabase.table("transactions_staging") \
            .update({"is_confirmed": True}) \
            .eq("id", txn.id) \
            .execute()

        confirmed_count += 1

    if confirmed_count == 0:
        raise HTTPException(status_code=400, detail="No valid staging transactions were confirmed")

    # Retrain cached model once at the end of batch confirmation.
    ml_service.refresh_user_model(user["id"])

    return {"status": "confirmed", "count": confirmed_count}



