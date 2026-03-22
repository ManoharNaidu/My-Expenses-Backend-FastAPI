"""Tests for core/otp.py — OTP generation, hashing, insert and consume."""
import hashlib
from unittest.mock import MagicMock, call, patch

import pytest
from fastapi import HTTPException

from core.otp import (
    _hash_otp,
    check_resend_rate_limit,
    consume_otp,
    generate_otp,
    insert_otp,
)


def test_generate_otp_is_6_digits():
    otp = generate_otp()
    assert len(otp) == 6
    assert otp.isdigit()


def test_generate_otp_varies():
    otps = {generate_otp() for _ in range(20)}
    assert len(otps) > 1  # very unlikely to be all identical


def test_hash_otp_is_sha256():
    raw = "123456"
    expected = hashlib.sha256(raw.encode()).hexdigest()
    assert _hash_otp(raw) == expected
    assert len(_hash_otp(raw)) == 64  # SHA-256 hex digest length


def test_insert_otp_stores_hash(reset_supabase_mock):
    from tests.conftest import mock_supabase
    chain = MagicMock()
    chain.execute.return_value = MagicMock()
    mock_supabase.table.return_value.insert.return_value = chain

    insert_otp("email_verification", "user-1", "654321")

    inserted = mock_supabase.table.return_value.insert.call_args[0][0]
    assert inserted["otp"] == _hash_otp("654321")
    assert inserted["user_id"] == "user-1"
    assert inserted["used"] is False


def test_consume_otp_marks_used(reset_supabase_mock):
    from tests.conftest import mock_supabase

    fake_row = {"id": "otp-row-1", "expires_at": "2099-01-01T00:00:00+00:00", "used": False}
    select_chain = MagicMock()
    select_chain.execute.return_value = MagicMock(data=[fake_row])
    (
        mock_supabase.table.return_value
        .select.return_value
        .eq.return_value
        .eq.return_value
        .eq.return_value
        .gte.return_value
        .order.return_value
        .limit.return_value
    ) = select_chain

    update_chain = MagicMock()
    update_chain.execute.return_value = MagicMock()
    mock_supabase.table.return_value.update.return_value.eq.return_value = update_chain

    consume_otp("email_verification", "user-1", "123456")

    # Verify update was called with used=True
    mock_supabase.table.return_value.update.assert_called_with({"used": True})


def test_consume_otp_raises_on_invalid(reset_supabase_mock):
    from tests.conftest import mock_supabase

    select_chain = MagicMock()
    select_chain.execute.return_value = MagicMock(data=[])  # nothing found
    (
        mock_supabase.table.return_value
        .select.return_value
        .eq.return_value
        .eq.return_value
        .eq.return_value
        .gte.return_value
        .order.return_value
        .limit.return_value
    ) = select_chain

    with pytest.raises(HTTPException) as exc_info:
        consume_otp("email_verification", "user-1", "000000")
    assert exc_info.value.status_code == 400


def test_check_resend_rate_limit_allows_under_limit(reset_supabase_mock):
    from tests.conftest import mock_supabase

    result = MagicMock()
    result.count = 2
    (
        mock_supabase.table.return_value
        .select.return_value
        .eq.return_value
        .gte.return_value
        .execute.return_value
    ) = result

    # Should not raise
    check_resend_rate_limit("user-1", "email_verification")


def test_check_resend_rate_limit_blocks_at_limit(reset_supabase_mock):
    from tests.conftest import mock_supabase

    result = MagicMock()
    result.count = 5  # at the limit
    (
        mock_supabase.table.return_value
        .select.return_value
        .eq.return_value
        .gte.return_value
        .execute.return_value
    ) = result

    with pytest.raises(HTTPException) as exc_info:
        check_resend_rate_limit("user-1", "email_verification")
    assert exc_info.value.status_code == 429


@pytest.fixture
def reset_supabase_mock():
    from tests.conftest import mock_supabase
    mock_supabase.reset_mock()
    yield
    mock_supabase.reset_mock()
