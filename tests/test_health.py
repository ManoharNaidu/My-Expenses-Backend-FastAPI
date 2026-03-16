"""Tests for health / root endpoints."""
from unittest.mock import MagicMock


def test_root(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["message"] == "Welcome to the Expense Automation API!"
    assert body["api_version"] == "1"


def test_health_liveness(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_ready_db_up(client, mock_supabase_fixture):
    """Readiness returns ok when DB query succeeds."""
    from tests.conftest import mock_supabase
    chain = MagicMock()
    chain.execute.return_value = MagicMock(data=[{"id": "1"}])
    mock_supabase.from_.return_value.select.return_value.limit.return_value = chain

    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_health_ready_db_down(client):
    """Readiness returns 503 when DB query raises."""
    from tests.conftest import mock_supabase
    mock_supabase.from_.side_effect = Exception("DB unreachable")

    resp = client.get("/health/ready")
    assert resp.status_code == 503
    mock_supabase.from_.side_effect = None  # cleanup


import pytest

@pytest.fixture
def mock_supabase_fixture():
    from tests.conftest import mock_supabase
    from unittest.mock import MagicMock
    chain = MagicMock()
    chain.execute.return_value = MagicMock(data=[])
    mock_supabase.from_.return_value.select.return_value.limit.return_value = chain
    yield
