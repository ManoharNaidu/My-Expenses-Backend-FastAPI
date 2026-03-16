"""Tests for /api/v1/transactions routes."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import auth_headers, make_user, mock_supabase


def _setup_auth(user: dict | None = None):
    """Wire mock so get_current_user resolves correctly."""
    u = user or make_user()
    id_chain = MagicMock()
    id_chain.execute.return_value = MagicMock(data=[u])
    mock_supabase.from_.return_value.select.return_value.eq.return_value.limit.return_value = id_chain
    return u


class TestGetTransactions:
    def test_returns_list(self, client):
        user = _setup_auth()
        tx_chain = MagicMock()
        tx_chain.execute.return_value = MagicMock(data=[
            {"id": "t1", "amount": 50.0, "type": "expense", "category": "Food", "date": "2026-01-01"},
        ])
        (
            mock_supabase.table.return_value
            .select.return_value
            .eq.return_value
            .order.return_value
            .range.return_value
        ) = tx_chain

        resp = client.get("/api/v1/transactions", headers=auth_headers())
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/api/v1/transactions")
        assert resp.status_code == 401

    def test_limit_clamped_to_100(self, client):
        _setup_auth()
        tx_chain = MagicMock()
        tx_chain.execute.return_value = MagicMock(data=[])
        (
            mock_supabase.table.return_value
            .select.return_value
            .eq.return_value
            .order.return_value
            .range.return_value
        ) = tx_chain

        # Even if limit=9999 is passed, server clamps it
        resp = client.get("/api/v1/transactions?limit=9999", headers=auth_headers())
        assert resp.status_code == 200


class TestCreateTransaction:
    def test_creates_transaction_successfully(self, client):
        _setup_auth()
        ins_chain = MagicMock()
        ins_chain.execute.return_value = MagicMock(
            data=[{"id": "new-tx", "amount": 25.0, "type": "expense"}]
        )
        mock_supabase.table.return_value.insert.return_value = ins_chain

        with patch("routes.transactions.ml_service.refresh_user_model"):
            resp = client.post("/api/v1/transactions", headers=auth_headers(), json={
                "amount": 25.0,
                "date": "2026-03-01T00:00:00",
                "type": "expense",
                "category": "Food",
                "repeat_monthly": False,
            })
        assert resp.status_code == 200
        assert resp.json()["message"] == "Transaction added"

    def test_income_type_normalised(self, client):
        _setup_auth()
        inserted_records = []

        def capture_insert(record):
            inserted_records.append(record)
            chain = MagicMock()
            chain.execute.return_value = MagicMock(data=[record])
            return chain

        mock_supabase.table.return_value.insert.side_effect = capture_insert

        with patch("routes.transactions.ml_service.refresh_user_model"):
            resp = client.post("/api/v1/transactions", headers=auth_headers(), json={
                "amount": 100.0,
                "date": "2026-03-01T00:00:00",
                "type": "credit",   # should be normalised to "income"
                "category": "Job",
                "repeat_monthly": False,
            })
        assert resp.status_code == 200
        assert inserted_records[0]["type"] == "income"

    def test_missing_required_fields_returns_422(self, client):
        _setup_auth()
        resp = client.post("/api/v1/transactions", headers=auth_headers(), json={
            "amount": 10.0,
        })
        assert resp.status_code == 422


class TestDeleteTransaction:
    def test_delete_returns_success(self, client):
        _setup_auth()
        del_chain = MagicMock()
        del_chain.execute.return_value = MagicMock()
        (
            mock_supabase.table.return_value
            .delete.return_value
            .eq.return_value
            .eq.return_value
        ) = del_chain

        resp = client.delete("/api/v1/transactions/tx-1", headers=auth_headers())
        assert resp.status_code == 200
        assert resp.json()["message"] == "Transaction deleted"


class TestBudgetGoal:
    def test_get_budget_goal_returns_defaults_when_none(self, client):
        _setup_auth()
        chain = MagicMock()
        chain.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value = chain

        resp = client.get("/api/v1/budget-goal", headers=auth_headers())
        assert resp.status_code == 200
        assert resp.json()["monthly_limit"] == 0

    def test_update_budget_goal_creates_new(self, client):
        _setup_auth()
        # No existing record
        sel_chain = MagicMock()
        sel_chain.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value = sel_chain

        ins_chain = MagicMock()
        ins_chain.execute.return_value = MagicMock(
            data=[{"monthly_limit": 500.0, "alerts_enabled": True}]
        )
        mock_supabase.table.return_value.insert.return_value = ins_chain

        resp = client.put("/api/v1/budget-goal", headers=auth_headers(), json={
            "monthly_limit": 500.0,
            "alerts_enabled": True,
        })
        assert resp.status_code == 200


class TestConfirmStaging:
    def test_empty_payload_returns_400(self, client):
        _setup_auth()
        resp = client.post("/api/v1/confirm-staging-transactions",
                           headers=auth_headers(), json=[])
        assert resp.status_code == 400

    def test_valid_payload_confirmed(self, client):
        _setup_auth()
        staging_row = {
            "id": "staging-1",
            "user_id": "user-123",
            "date": "2026-03-01",
            "description": "Lunch",
            "amount": 15.0,
            "predicted_type": "expense",
            "predicted_category": "Food",
        }
        # batch fetch staging
        fetch_chain = MagicMock()
        fetch_chain.execute.return_value = MagicMock(data=[staging_row])
        (
            mock_supabase.table.return_value
            .select.return_value
            .in_.return_value
            .eq.return_value
        ) = fetch_chain

        ins_chain = MagicMock()
        ins_chain.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value.insert.return_value = ins_chain

        upd_chain = MagicMock()
        upd_chain.execute.return_value = MagicMock()
        mock_supabase.table.return_value.update.return_value.in_.return_value = upd_chain

        with patch("routes.transactions.ml_service.refresh_user_model"):
            resp = client.post(
                "/api/v1/confirm-staging-transactions",
                headers=auth_headers(),
                json=[{
                    "id": "staging-1",
                    "final_type": "expense",
                    "final_category": "Food",
                }],
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "confirmed"
