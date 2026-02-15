import shutil
import tempfile
import os

from fastapi import APIRouter, UploadFile, File, Depends

from pdf_parser import TransactionPDFExtractor
from core.database import supabase
from routes.auth import get_current_user

router = APIRouter()


@router.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...), user=Depends(get_current_user)):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
        temp_path = temp_file.name
        shutil.copyfileobj(file.file, temp_file)

    try:
        extractor = TransactionPDFExtractor(temp_path)
        transactions = extractor.extract()
        parser_used = extractor.last_parser_name
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass

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

    if records:
        supabase.table("transactions_staging").insert(records).execute()

    return {
        "message": "PDF processed",
        "transactions_detected": len(records),
        "parser_used": parser_used,
    }

@router.get("/staging-transactions")
def get_staging_transactions(user=Depends(get_current_user)):
    return supabase.table("transactions_staging") \
        .select("*") \
        .eq("user_id", user["id"]) \
        .order("date", desc=True) \
        .execute().data
