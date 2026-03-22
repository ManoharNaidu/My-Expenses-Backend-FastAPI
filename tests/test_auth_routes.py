"""
Integration-style tests for /api/v1/auth/* routes.
Supabase and email are fully mocked — no network calls.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import auth_headers, make_user, mock_supabase


# ── helpers ───────────────────────────────────────────────────────────────────

def _chain_user_query(user: dict | None):
    """Wire mock_supabase so a user-by-email lookup returns `user`."""
    chain = MagicMock()
    chain.execute.return_value = MagicMock(data=[user] if user else [])
    mock_supabase.from_.return_value.select.return_value.eq.return_value.limit.return_value = chain
    return chain


def _chain_insert():
    chain = MagicMock()
    chain.execute.return_value = MagicMock(data=[{"id": "new-id"}])
    mock_supabase.from_.return_value.insert.return_value = chain
    return chain


def _chain_otp_insert():
    chain = MagicMock()
    chain.execute.return_value = MagicMock()
    mock_supabase.table.return_value.insert.return_value = chain
    return chain


# ── /register ─────────────────────────────────────────────────────────────────

class TestRegister:
    def test_new_user_registration(self, client):
        _chain_user_query(None)   # no existing user
        _chain_insert()
        _chain_otp_insert()

        with patch("routes.auth.send_verification_email"):
            resp = client.post("/api/v1/auth/register", json={
                "name": "Alice",
                "email": "alice@example.com",
                "password": "password123",
            })

        assert resp.status_code == 200
        assert "verification code" in resp.json()["message"].lower()

    def test_already_verified_email_returns_400(self, client):
        user = make_user(email="existing@example.com")
        _chain_user_query(user)

        resp = client.post("/api/v1/auth/register", json={
            "name": "Alice",
            "email": "existing@example.com",
            "password": "password123",
        })
        assert resp.status_code == 400
        assert "already registered" in resp.json()["message"].lower()

    def test_unverified_reregistration_resends_otp(self, client):
        user = make_user(is_verified=False)
        _chain_user_query(user)
        update_chain = MagicMock()
        update_chain.execute.return_value = MagicMock()
        mock_supabase.from_.return_value.update.return_value.eq.return_value = update_chain
        _chain_otp_insert()

        with patch("routes.auth.send_verification_email"):
            resp = client.post("/api/v1/auth/register", json={
                "name": "Alice",
                "email": "alice@example.com",
                "password": "newpassword",
            })
        assert resp.status_code == 200

    def test_missing_required_fields_returns_422(self, client):
        resp = client.post("/api/v1/auth/register", json={"email": "x@x.com"})
        assert resp.status_code == 422

    def test_short_password_returns_422(self, client):
        resp = client.post("/api/v1/auth/register", json={
            "name": "Alice", "email": "a@b.com", "password": "short",
        })
        assert resp.status_code == 422


# ── /login ────────────────────────────────────────────────────────────────────

class TestLogin:
    def test_valid_credentials_returns_token(self, client):
        user = make_user(password="password123")
        _chain_user_query(user)

        resp = client.post("/api/v1/auth/login", json={
            "email": "test@example.com",
            "password": "password123",
        })
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_wrong_password_returns_401(self, client):
        user = make_user(password="correctpassword")
        _chain_user_query(user)

        resp = client.post("/api/v1/auth/login", json={
            "email": "test@example.com",
            "password": "wrongpassword",
        })
        assert resp.status_code == 401

    def test_nonexistent_user_returns_401(self, client):
        _chain_user_query(None)
        resp = client.post("/api/v1/auth/login", json={
            "email": "nobody@example.com",
            "password": "password123",
        })
        assert resp.status_code == 401

    def test_unverified_user_returns_403_with_flag(self, client):
        user = make_user(is_verified=False, password="password123")
        _chain_user_query(user)
        _chain_otp_insert()

        with patch("routes.auth._fire_and_forget"):
            resp = client.post("/api/v1/auth/login", json={
                "email": "test@example.com",
                "password": "password123",
            })
        assert resp.status_code == 403
        assert resp.json().get("requires_verification") is True

    def test_missing_email_returns_422(self, client):
        resp = client.post("/api/v1/auth/login", json={"password": "pass"})
        assert resp.status_code == 422


# ── /me ───────────────────────────────────────────────────────────────────────

class TestMe:
    def test_authenticated_returns_profile(self, client):
        user = make_user()
        # user-by-id lookup (used by get_current_user)
        id_chain = MagicMock()
        id_chain.execute.return_value = MagicMock(data=[user])
        mock_supabase.from_.return_value.select.return_value.eq.return_value.limit.return_value = id_chain

        # app_locks lookup
        lock_chain = MagicMock()
        lock_chain.execute.return_value = MagicMock(data=[])
        mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value = lock_chain

        resp = client.get("/api/v1/auth/me", headers=auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == user["email"]
        assert data["name"] == user["name"]

    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self, client):
        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer totally.invalid.token"},
        )
        assert resp.status_code == 401

    def test_revoked_token_returns_401(self, client):
        """token_version mismatch should be rejected."""
        user = make_user(token_version=5)
        id_chain = MagicMock()
        id_chain.execute.return_value = MagicMock(data=[user])
        mock_supabase.from_.return_value.select.return_value.eq.return_value.limit.return_value = id_chain

        # Token was issued with ver=0 but user now has token_version=5
        headers = auth_headers(token_version=0)
        resp = client.get("/api/v1/auth/me", headers=headers)
        assert resp.status_code == 401
        assert "revoked" in resp.json()["message"].lower()


# ── /forgot-password & /reset-password ───────────────────────────────────────

class TestPasswordReset:
    def test_forgot_password_unknown_email_returns_404(self, client):
        _chain_user_query(None)
        resp = client.post("/api/v1/auth/forgot-password", json={"email": "x@x.com"})
        assert resp.status_code == 404

    def test_forgot_password_known_email_returns_200(self, client):
        user = make_user()
        _chain_user_query(user)
        # rate limit check
        rl_chain = MagicMock()
        rl_chain.execute.return_value = MagicMock(count=0)
        mock_supabase.table.return_value.select.return_value.eq.return_value.gte.return_value = rl_chain
        _chain_otp_insert()

        with patch("routes.auth.send_password_reset_email"):
            resp = client.post("/api/v1/auth/forgot-password", json={"email": "test@example.com"})
        assert resp.status_code == 200
        assert "reset code" in resp.json()["message"].lower()

    def test_reset_password_invalid_otp_returns_400(self, client):
        user = make_user()
        _chain_user_query(user)
        # OTP lookup returns nothing
        otp_chain = MagicMock()
        otp_chain.execute.return_value = MagicMock(data=[])
        (
            mock_supabase.table.return_value
            .select.return_value
            .eq.return_value
            .eq.return_value
            .eq.return_value
            .gte.return_value
            .order.return_value
            .limit.return_value
        ) = otp_chain

        resp = client.post("/api/v1/auth/reset-password", json={
            "email": "test@example.com",
            "otp": "000000",
            "new_password": "newpassword123",
        })
        assert resp.status_code == 400
