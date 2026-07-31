"""Tests for API app — endpoint availability and middleware."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


@pytest.fixture
def client():
    """Create test client with mocked storage."""
    with patch("trading_system.api.app.storage") as mock_storage:
        mock_storage.get_source_health.return_value = MagicMock(to_dict=MagicMock(return_value=[]))
        mock_storage.list_tickers.return_value = ["BBCA.JK"]
        mock_storage.load_ohlcv.return_value = MagicMock(empty=True)
        mock_storage.load_scores.return_value = MagicMock(empty=True)
        from trading_system.api.app import app
        yield TestClient(app)


def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200


def test_tickers_endpoint(client):
    response = client.get("/api/tickers")
    assert response.status_code == 200
    data = response.json()
    assert "tickers" in data
    assert "count" in data


def test_engines_endpoint(client):
    response = client.get("/api/engines")
    assert response.status_code == 200
    data = response.json()
    assert "engines" in data
    assert "timestamp" in data


def test_engines_registry_has_18(client):
    from trading_system.api.app import ENGINE_REGISTRY
    assert len(ENGINE_REGISTRY) == 18


def test_engines_registry_includes_new():
    from trading_system.api.app import ENGINE_REGISTRY
    names = [e["name"] for e in ENGINE_REGISTRY]
    assert "automated_execution" in names
    assert "rebalancer" in names
    assert "performance_analytics" in names


def test_cors_headers(client):
    response = client.get("/", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") is not None


def test_rate_limit_not_triggered(client):
    """Single request should not trigger rate limit."""
    response = client.get("/")
    assert response.status_code == 200


def test_watchlist_endpoint(client):
    with patch("trading_system.api.app.storage") as mock_storage:
        mock_storage.get_watchlist.return_value = []
        response = client.get("/api/watchlist")
        assert response.status_code == 200
