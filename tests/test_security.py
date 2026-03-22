"""Tests for core/security.py — password hashing and JWT."""
import time

import pytest

from core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


# ── password ──────────────────────────────────────────────────────────────────

def test_hash_password_returns_bcrypt_string():
    h = hash_password("secret123")
    assert h.startswith("$2b$")


def test_verify_password_correct():
    h = hash_password("mypassword")
    assert verify_password("mypassword", h) is True


def test_verify_password_wrong():
    h = hash_password("mypassword")
    assert verify_password("wrongpassword", h) is False


def test_hash_is_unique():
    """Two hashes of the same password must differ (bcrypt salting)."""
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2


# ── JWT ───────────────────────────────────────────────────────────────────────

def test_create_and_decode_token():
    token = create_access_token({"sub": "user-abc", "ver": 0})
    payload = decode_access_token(token)
    assert payload["sub"] == "user-abc"
    assert payload["ver"] == 0


def test_decode_invalid_token_raises():
    import jwt
    with pytest.raises(jwt.PyJWTError):
        decode_access_token("totally.invalid.token")


def test_token_carries_extra_claims():
    token = create_access_token({"sub": "u1", "ver": 3, "custom": "value"})
    payload = decode_access_token(token)
    assert payload["custom"] == "value"
    assert payload["ver"] == 3


def test_expired_token_raises(monkeypatch):
    """Simulate an already-expired token."""
    import jwt as pyjwt
    from datetime import datetime, timezone
    from core.config import JWT_SECRET, JWT_ALGORITHM

    past = datetime(2000, 1, 1, tzinfo=timezone.utc)
    token = pyjwt.encode({"sub": "u1", "exp": past}, JWT_SECRET, algorithm=JWT_ALGORITHM)
    with pytest.raises(pyjwt.ExpiredSignatureError):
        decode_access_token(token)
