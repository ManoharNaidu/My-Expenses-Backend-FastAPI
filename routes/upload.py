import shutil
import tempfile

from fastapi import APIRouter, UploadFile, File, Depends
from websockets import route

from pdf_parser import TransactionPDFExtractor
from core.database import supabase
from routes.auth import get_current_user

router = APIRouter()


@router.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...), user=Depends(get_current_user)):
    temp_path = tempfile.mktemp(suffix=".pdf")

    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    extractor = TransactionPDFExtractor(temp_path)
    transactions = extractor.extract()

    records = []
    for t in transactions:
        records.append({
            "user_id": user["id"],
            "date": t.date.date().isoformat(),
            "original_date": t.date.date().isoformat(),
            "description": t.description,
            "amount": t.amount,
            "predicted_type": t.transaction_type,
            "predicted_category": "unknown",
            "is_confirmed": False,
        })

    supabase.table("transactions_staging").insert(records).execute()

    return {
        "message": "PDF processed",
        "transactions_detected": len(records),
    }

@router.post("/confirm-staging-transactions")
def confirm_transactions(user=Depends(get_current_user)):
    # Move all staging transactions to main transactions table
    staging_transactions = supabase.table("transactions_staging") \
        .select("*") \
        .eq("user_id", user["id"]) \
        .eq("is_confirmed", False) \
        .execute().data

    if not staging_transactions:
        return {"message": "No staging transactions to confirm"}

    records = []
    for t in staging_transactions:
        records.append({
            "user_id": t["user_id"],
            "date": t["date"],
            "original_date": t["original_date"],
            "description": t["description"],
            "amount": t["amount"],
            "type": t["predicted_type"],
            "category": t["predicted_category"],
        })

    supabase.table("transactions").insert(records).execute()


    ml_feedback_records = []
    for t in staging_transactions:
        ml_feedback_records.append({
            "user_id": t["user_id"],
            "date": t["date"],
            "description": t["description"],
            "amount": t["amount"],
            "predicted_type": t["predicted_type"],
            "predicted_category": t["predicted_category"],
            "is_confirmed": True,
        })
    supabase.table("ml_feedback").insert(records).execute()

    # Delete confirmed staging transactions
    supabase.table("transactions_staging") \
        .delete() \
        .eq("user_id", user["id"]) \
        .eq("is_confirmed", False) \
        .execute()

    return {"message": f"Confirmed {len(records)} transactions"}

@router.get("/staging-transactions")
def get_staging_transactions(user=Depends(get_current_user)):
    return supabase.table("transactions_staging") \
        .select("*") \
        .eq("user_id", user["id"]) \
        .order("date", desc=True) \
        .execute().data
