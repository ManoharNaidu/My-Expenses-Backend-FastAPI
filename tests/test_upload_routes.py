"""Tests for PDF upload staging responses."""
from __future__ import annotations

import datetime
from io import BytesIO
from unittest.mock import MagicMock, patch

from tests.conftest import auth_headers, make_user, mock_supabase


def _setup_auth(user: dict | None = None):
    u = user or make_user()
    id_chain = MagicMock()
    id_chain.execute.return_value = MagicMock(data=[u])
    mock_supabase.from_.return_value.select.return_value.eq.return_value.limit.return_value = id_chain
    return u


class TestUploadPdf:
    def test_upload_returns_inserted_staging_rows(self, client, tmp_path):
        _setup_auth()

        extractor_instance = MagicMock()
        extractor_instance.extract.return_value = [
            MagicMock(
                date=datetime.datetime(2026, 3, 1),
                description="Lunch",
                amount=12.5,
                transaction_type="expense",
            )
        ]
        extractor_instance.last_parser_name = "table"

        insert_chain = MagicMock()
        insert_chain.execute.return_value = MagicMock(
            data=[
                {
                    "id": "staging-1",
                    "user_id": "user-123",
                    "date": "2026-03-01",
                    "description": "Lunch",
                    "amount": 12.5,
                    "predicted_type": "expense",
                    "predicted_category": "Food",
                    "is_confirmed": False,
                }
            ]
        )
        mock_supabase.table.return_value.insert.return_value = insert_chain

        pdf_bytes = BytesIO(b"%PDF-1.4 test pdf bytes")
        with patch("routes.upload.TransactionPDFExtractor", return_value=extractor_instance), \
             patch("routes.upload.ml_service.predict", return_value=("expense", "Food")), \
             patch("routes.upload.os.remove"):
            resp = client.post(
                "/api/v1/upload-pdf",
                headers=auth_headers(),
                files={"file": ("statement.pdf", pdf_bytes, "application/pdf")},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["transactions_detected"] == 1
        assert body["transactions"][0]["id"] == "staging-1"
        assert body["transactions"][0]["predicted_category"] == "Food"
