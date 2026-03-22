"""Tests for core/ml_classifier.py — thread safety and prediction logic."""
from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest

from core.ml_classifier import TransactionMLService, _map_statement_type, _normalize_description


# ── pure functions ────────────────────────────────────────────────────────────

def test_normalize_description_lowercases():
    assert _normalize_description("GROCERY STORE") == "grocery store"


def test_normalize_description_strips_punctuation():
    result = _normalize_description("7-Eleven! Coffee & Food.")
    assert "!" not in result
    assert "&" not in result


def test_normalize_description_collapses_whitespace():
    assert _normalize_description("  lots   of   spaces  ") == "lots of spaces"


def test_normalize_description_empty():
    assert _normalize_description("") == ""
    assert _normalize_description(None) == ""


def test_map_statement_type_credit():
    assert _map_statement_type("credit") == "income"
    assert _map_statement_type("income") == "income"
    assert _map_statement_type("CREDIT") == "income"


def test_map_statement_type_debit():
    assert _map_statement_type("debit") == "expense"
    assert _map_statement_type("expense") == "expense"


def test_map_statement_type_unknown_defaults_expense():
    assert _map_statement_type("random") == "expense"
    assert _map_statement_type(None) == "expense"


# ── ML service ────────────────────────────────────────────────────────────────

def _mock_supabase_for_training(mock_sb, transactions=None, feedback=None):
    """Helper: set up supabase mock to return training data."""
    txn_chain = MagicMock()
    txn_chain.execute.return_value = MagicMock(data=transactions or [])
    mock_sb.table.return_value.select.return_value.eq.return_value = txn_chain

    fb_chain = MagicMock()
    fb_chain.execute.return_value = MagicMock(data=feedback or [])
    # second call to .eq() on feedback table
    return txn_chain, fb_chain


def test_predict_returns_tuple(monkeypatch):
    from tests.conftest import mock_supabase
    mock_supabase.reset_mock()

    # No training data → cold start fallback
    chain = MagicMock()
    chain.execute.return_value = MagicMock(data=[])
    mock_supabase.table.return_value.select.return_value.eq.return_value = chain

    svc = TransactionMLService()
    result = svc.predict("user-1", "coffee shop")
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert result[0] in ("income", "expense")


def test_predict_cold_start_uses_fallback_type(monkeypatch):
    from tests.conftest import mock_supabase
    mock_supabase.reset_mock()

    chain = MagicMock()
    chain.execute.return_value = MagicMock(data=[])
    mock_supabase.table.return_value.select.return_value.eq.return_value = chain

    svc = TransactionMLService()
    tx_type, _ = svc.predict("user-1", "salary", fallback_statement_type="credit")
    assert tx_type == "income"


def test_predict_empty_description_uses_fallback():
    from tests.conftest import mock_supabase
    mock_supabase.reset_mock()

    chain = MagicMock()
    chain.execute.return_value = MagicMock(data=[])
    mock_supabase.table.return_value.select.return_value.eq.return_value = chain

    svc = TransactionMLService()
    tx_type, category = svc.predict("user-1", "   ", fallback_statement_type="debit")
    assert tx_type == "expense"
    assert category == "unknown"


def test_cache_is_thread_safe():
    """Multiple threads refreshing the same user model must not corrupt cache."""
    from tests.conftest import mock_supabase
    mock_supabase.reset_mock()

    chain = MagicMock()
    chain.execute.return_value = MagicMock(data=[])
    mock_supabase.table.return_value.select.return_value.eq.return_value = chain

    svc = TransactionMLService()
    errors = []

    def refresh():
        try:
            svc.refresh_user_model("user-thread-test")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=refresh) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"Thread safety errors: {errors}"


def test_refresh_updates_cache():
    from tests.conftest import mock_supabase
    mock_supabase.reset_mock()

    chain = MagicMock()
    chain.execute.return_value = MagicMock(data=[])
    mock_supabase.table.return_value.select.return_value.eq.return_value = chain

    svc = TransactionMLService()
    model1 = svc.refresh_user_model("user-cache-test")
    model2 = svc._get_user_model("user-cache-test")
    # After refresh, cached model is returned (same object)
    assert model1 is model2
