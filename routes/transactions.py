from fastapi import APIRouter, Depends

from core.database import supabase
from models.transactions import TransactionConfirm, TransactionCreate
from routes.auth import get_current_user

router = APIRouter()


@router.get("/transactions")
def get_user_transactions(user=Depends(get_current_user)):
    return supabase.table("transactions") \
        .select("*") \
        .eq("user_id", user["id"]) \
        .order("date", desc=True) \
        .execute().data


@router.post("/transactions")
def create_transaction(data: TransactionCreate, user=Depends(get_current_user)):
    
    record = {
        "user_id": user["id"],
        "date": data.date.isoformat(),
        "original_date": data.original_date.isoformat(),
        "description": data.description,
        "amount": data.amount,
        "type": data.type,
        "category": data.category,
    }

    result = supabase.table("transactions").insert(record).execute()

    return {"message": "Transaction added", "transaction": result.data[0]}


@router.get("/staging")
def get_staging_transactions(user=Depends(get_current_user)):
    return supabase.table("transactions_staging") \
        .select("*") \
        .eq("user_id", user["id"]) \
        .eq("is_confirmed", False) \
        .execute().data


@router.post("/confirm")
def confirm_transactions(payload: list[TransactionConfirm], user=Depends(get_current_user)):
    for txn in payload:
        # fetch staging (scoped to user)
        row = supabase.table("transactions_staging") \
            .select("*") \
            .eq("id", txn.id) \
            .eq("user_id", user["id"]) \
            .single() \
            .execute().data

        # insert final
        supabase.table("transactions").insert({
            "user_id": user["id"],
            "date": row["date"],
            "original_date": row["original_date"],
            "description": row["description"],
            "amount": row["amount"],
            "type": txn.final_type,
            "category": txn.final_category,
        }).execute()

        # ML feedback
        supabase.table("ml_feedback").insert({
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

    return {"status": "confirmed"}

