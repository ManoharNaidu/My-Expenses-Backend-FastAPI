import os
import shutil
import tempfile

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from core.config import MAX_UPLOAD_BYTES

from core.database import supabase
from core.ml_classifier import ml_service
from pdf_parser import TransactionPDFExtractor
from routes.auth import get_current_user

router = APIRouter()

ALLOWED_CONTENT_TYPES = {"application/pdf"}

def _extract_pdf(temp_path: str):
    extractor = TransactionPDFExtractor(temp_path)
    return extractor.extract(), extractor.last_parser_name


@router.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...), user=Depends(get_current_user)):
    print(f"Received file: {file.filename}, content type: {file.content_type}")
    if file.content_type and file.content_type.lower() not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    if file.size and file.size > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File size exceeds limit of {MAX_UPLOAD_BYTES} bytes")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file not allowed")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File size exceeds limit of {MAX_UPLOAD_BYTES} bytes")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
        temp_path = temp_file.name
        temp_file.write(content)

    try:
        transactions, parser_used = await run_in_threadpool(_extract_pdf, temp_path)
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass

    records = []
    for t in transactions:
        predicted_type, predicted_category = ml_service.predict(
            user_id=user["id"],
            description=t.description,
            fallback_statement_type=t.transaction_type,
        )

        records.append({
            "user_id": user["id"],
            "date": t.date.date().isoformat(),
            "description": t.description,
            "amount": t.amount,
            "predicted_type": predicted_type,
            "predicted_category": predicted_category,
            "is_confirmed": False,
        })

    if records:
        supabase.table("transactions_staging").insert(records).execute()

    return {
        "message": "PDF processed",
        "transactions_detected": len(records),
        "parser_used": parser_used,
    }
