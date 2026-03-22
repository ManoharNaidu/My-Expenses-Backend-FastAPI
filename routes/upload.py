import asyncio
import os
import tempfile

from fastapi import APIRouter, File, HTTPException, UploadFile, Depends

from core.config import MAX_UPLOAD_BYTES
from core.database import supabase
from core.ml_classifier import ml_service
from pdf_parser import TransactionPDFExtractor
from routes.auth import get_current_user

router = APIRouter()

ALLOWED_CONTENT_TYPES = {"application/pdf"}


@router.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...), user=Depends(get_current_user)):
    if file.content_type and file.content_type.lower() not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    # Enforce size limit before writing to disk
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file not allowed")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp_path = tmp.name
        tmp.write(content)

    try:
        extractor = TransactionPDFExtractor(tmp_path)
        # Offload CPU-bound PDF parsing to a thread so the event loop stays free
        transactions = await asyncio.to_thread(extractor.extract)
        parser_used = extractor.last_parser_name
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    records = []
    for t in transactions:
        predicted_type, predicted_category = ml_service.predict(
            user_id=user["id"],
            description=t.description,
            fallback_statement_type=t.transaction_type,
        )
        records.append(
            {
                "user_id": user["id"],
                "date": t.date.date().isoformat(),
                "description": t.description,
                "amount": t.amount,
                "predicted_type": predicted_type,
                "predicted_category": predicted_category,
                "is_confirmed": False,
            }
        )

    if records:
        supabase.table("transactions_staging").insert(records).execute()

    return {
        "message": "PDF processed",
        "transactions_detected": len(records),
        "parser_used": parser_used,
    }
