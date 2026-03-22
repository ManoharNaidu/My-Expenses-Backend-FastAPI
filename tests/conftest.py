"""
Shared fixtures for all tests.

All Supabase calls are mocked via pytest-mock / unittest.mock so tests
run fully offline with no real DB or email credentials required.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ── make sure we can import from the project root ────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ── stub out env vars BEFORE importing anything that reads them ──────────────
os.environ.setdefault("JWT_SECRET", "test-secret-key-that-is-32-chars!!")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-supabase-key")
os.environ.setdefault("BREVO_API_KEY", "test-brevo-api-key-minimum-length")
os.environ.setdefault("SENDER_EMAIL", "test@example.com")
os.environ.setdefault("JWT_EXPIRE_MINUTES", "60")

# ── mock the supabase client before it is imported by any route ──────────────
mock_supabase = MagicMock()
patch("core.database.supabase", mock_supabase).start()
patch("core.otp.supabase", mock_supabase).start()
patch("routes.auth.supabase", mock_supabase).start()
patch("routes.transactions.supabase", mock_supabase).start()
patch("routes.health.supabase", mock_supabase).start()
patch("routes.feedback.supabase", mock_supabase).start()
patch("routes.settings.supabase", mock_supabase).start()
patch("routes.onboarding.supabase", mock_supabase).start()
patch("core.ml_classifier.supabase", mock_supabase).start()


@pytest.fixture(autouse=True)
def reset_supabase_mock():
    """Reset mock state between tests so calls don't bleed across."""
    mock_supabase.reset_mock()
    yield
    mock_supabase.reset_mock()


@pytest.fixture(scope="session")
def client():
    from main import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ── helpers used by multiple test modules ────────────────────────────────────

def make_user(
    user_id: str = "user-123",
    email: str = "test@example.com",
    name: str = "Test User",
    is_verified: bool = True,
    is_onboarded: bool = True,
    token_version: int = 0,
    password: str = "password123",
) -> dict:
    import bcrypt
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    return {
        "id": user_id,
        "email": email,
        "name": name,
        "password_hash": pw_hash,
        "is_verified": is_verified,
        "is_onboarded": is_onboarded,
        "token_version": token_version,
        "currency": "AUD",
    }


def make_token(user_id: str = "user-123", token_version: int = 0) -> str:
    from core.security import create_access_token
    return create_access_token({"sub": user_id, "ver": token_version})


def auth_headers(user_id: str = "user-123", token_version: int = 0) -> dict:
    return {"Authorization": f"Bearer {make_token(user_id, token_version)}"}
