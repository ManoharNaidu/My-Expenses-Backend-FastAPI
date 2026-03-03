import shutil
import tempfile
import os

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException

from core.config import MAX_UPLOAD_BYTES
from core.database import supabase
from pdf_parser import TransactionPDFExtractor
from routes.auth import get_current_user

router = APIRouter()

ALLOWED_CONTENT_TYPES = {"application/pdf"}


@router.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...), user=Depends(get_current_user)):
    if file.content_type and file.content_type.lower() not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size: {MAX_UPLOAD_BYTES} bytes",
        )
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file not allowed")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
        temp_path = temp_file.name
        temp_file.write(content)

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
