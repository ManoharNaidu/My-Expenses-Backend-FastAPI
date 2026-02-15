from fastapi import APIRouter, Depends, HTTPException

from core.database import supabase
from models.transactions import TransactionConfirm, TransactionCreate
from routes.auth import get_current_user

router = APIRouter()


@router.get("/transactions") #/transactions?limit=10&offset=0
def get_user_transactions(user=Depends(get_current_user), limit: int = 10, offset: int = 0):
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
        "original_date": data.original_date.isoformat(),
        "description": data.description,
        "amount": data.amount,
        "type": data.type,
        "category": data.category,
    }

    result = supabase.table("transactions").insert(record).execute()

    return {"message": "Transaction added", "transaction": result.data[0]}

@router.put("/transactions/{transaction_id}")
def update_transaction(transaction_id: str, data: TransactionCreate, user=Depends(get_current_user)):
    record = {
        "date": data.date.isoformat(),
        "original_date": data.original_date.isoformat(),
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

    return {"message": "Transaction updated", "transaction": result.data[0]}

@router.get("/staging")
def get_staging_transactions(user=Depends(get_current_user)):
    return supabase.table("transactions_staging") \
        .select("*") \
        .eq("user_id", user["id"]) \
        .eq("is_confirmed", False) \
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

        confirmed_count += 1

    if confirmed_count == 0:
        raise HTTPException(status_code=400, detail="No valid staging transactions were confirmed")

    return {"status": "confirmed", "count": confirmed_count}


