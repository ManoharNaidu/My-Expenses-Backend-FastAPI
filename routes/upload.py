import shutil
import tempfile

from fastapi import APIRouter, UploadFile, File

from pdf_parser import TransactionPDFExtractor
from core.database import supabase

router = APIRouter()


@router.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    temp_path = tempfile.mktemp(suffix=".pdf")
    print(temp_path)

    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    extractor = TransactionPDFExtractor(temp_path)
    transactions = extractor.extract()

    records = []
    for t in transactions:
        records.append({
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

