import os
from fastapi import FastAPI, UploadFile, File
from uuid import uuid4
import shutil
from pdf_parser import TransactionPDFExtractor
from supabase_client import supabase
from models import TransactionConfirm
import tempfile

app = FastAPI(title="Expense Automation API")

port = os.getenv("PORT", 8000)


# ---------------- Upload & Parse PDF ----------------

@app.post("/upload-pdf")
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


# ---------------- Review Transactions ----------------

@app.get("/staging")
def get_staging_transactions():
    return supabase.table("transactions_staging") \
        .select("*") \
        .eq("is_confirmed", False) \
        .execute().data


# ---------------- Confirm Transactions ----------------

@app.post("/confirm")
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
