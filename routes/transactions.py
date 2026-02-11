from fastapi import APIRouter

from core.database import supabase
from models.transactions import TransactionConfirm

router = APIRouter()


@router.get("/staging")
def get_staging_transactions():
    return supabase.table("transactions_staging") \
        .select("*") \
        .eq("is_confirmed", False) \
        .execute().data


@router.post("/confirm")
def confirm_transactions(payload: list[TransactionConfirm]):
    print(payload)
    for txn in payload:
        # fetch staging
        row = supabase.table("transactions_staging") \
            .select("*") \
            .eq("id", txn.id) \
            .single() \
            .execute().data

        # insert final
        supabase.table("transactions").insert({
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

