"""Tests for API app — endpoint availability and middleware."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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


class TestApiKeySecurity:
    """Regression tests for §3.5 SARAN_PENGEMBANGAN.md."""

    def test_sensitive_endpoint_disabled_without_api_key(self, client):
        """POST /api/execution/toggle harus 503 jika API_KEY tidak dikonfigurasi."""
        response = client.post("/api/execution/toggle", json={"enabled": True})
        assert response.status_code == 503

    def test_wrong_api_key_rejected(self, client, monkeypatch):
        import trading_system.api.app as app_module
        monkeypatch.setattr(app_module, "_API_KEY", "secret123")
        response = client.get("/api/tickers", headers={"X-API-Key": "wrong"})
        assert response.status_code == 401

    def test_correct_api_key_accepted(self, client, monkeypatch):
        import trading_system.api.app as app_module
        monkeypatch.setattr(app_module, "_API_KEY", "secret123")
        response = client.get("/api/tickers", headers={"X-API-Key": "secret123"})
        assert response.status_code == 200

    def test_valid_api_key_uses_constant_time_compare(self, monkeypatch):
        import trading_system.api.app as app_module
        monkeypatch.setattr(app_module, "_API_KEY", "secret123")
        assert app_module._valid_api_key("secret123") is True
        assert app_module._valid_api_key("wrong") is False
        assert app_module._valid_api_key("") is False

    def test_health_endpoint_accessible_without_key(self, client, monkeypatch):
        import trading_system.api.app as app_module
        monkeypatch.setattr(app_module, "_API_KEY", "secret123")
        response = client.get("/api/health")
        assert response.status_code == 200


class TestAuditLogEndpoint:
    """Test GET /api/audit endpoint."""

    def test_get_audit_logs(self, client):
        with patch("trading_system.api.app.storage") as mock_storage:
            mock_storage.get_audit_logs.return_value = [
                {"event_id": 1, "event_type": "test.event", "payload": "{}", "timestamp": "2024-01-01", "actor": "system"}
            ]
            response = client.get("/api/audit")
            assert response.status_code == 200
            data = response.json()
            assert "logs" in data
            assert data["count"] == 1

    def test_get_audit_logs_empty(self, client):
        with patch("trading_system.api.app.storage") as mock_storage:
            mock_storage.get_audit_logs.return_value = []
            response = client.get("/api/audit")
            assert response.status_code == 200
            assert response.json()["count"] == 0


class TestPortfolioExposureEndpoint:
    """Test GET /api/portfolio/exposure endpoint."""

    def test_exposure_with_no_positions(self, client):
        with patch("trading_system.api.app.storage") as mock_storage:
            mock_storage.get_all_open_positions.return_value = []
            mock_storage.get_equity_snapshots.return_value = []
            response = client.get("/api/portfolio/exposure")
            assert response.status_code == 200
            data = response.json()
            assert "cash" in data
            assert "invested" in data
            assert "total_equity" in data
            assert "exposure_pct" in data
            assert "position_count" in data
            assert data["invested"] == 0
            assert data["position_count"] == 0

    def test_exposure_with_positions(self, client):
        with patch("trading_system.api.app.storage") as mock_storage:
            mock_storage.get_all_open_positions.return_value = [
                {"ticker": "TEST.JK", "quantity": 100, "current_price": 5000, "avg_entry_price": 4500},
            ]
            mock_storage.get_equity_snapshots.return_value = [
                {"equity": 100000, "cash": 50000},
            ]
            response = client.get("/api/portfolio/exposure")
            assert response.status_code == 200
            data = response.json()
            assert data["invested"] == 500000
            assert data["position_count"] == 1


class TestDeleteEndpoints:
    """Test all DELETE endpoints."""

    def test_delete_ohlcv(self, client):
        with patch("trading_system.api.app.storage") as mock_storage:
            mock_storage.delete_ohlcv.return_value = 100
            mock_storage.audit = MagicMock()
            response = client.delete("/api/data/TEST.JK")
            assert response.status_code == 200
            assert response.json()["deleted"] == 100

    def test_delete_scores(self, client):
        with patch("trading_system.api.app.storage") as mock_storage:
            mock_storage.delete_scores.return_value = 5
            mock_storage.audit = MagicMock()
            response = client.delete("/api/scores/TEST.JK")
            assert response.status_code == 200
            assert response.json()["deleted"] == 5

    def test_delete_orders(self, client):
        with patch("trading_system.api.app.storage") as mock_storage:
            mock_storage.delete_orders.return_value = 10
            mock_storage.audit = MagicMock()
            response = client.delete("/api/orders")
            assert response.status_code == 200
            assert response.json()["deleted"] == 10

    def test_delete_audit_logs(self, client):
        with patch("trading_system.api.app.storage") as mock_storage:
            mock_storage.delete_audit_logs.return_value = 50
            response = client.delete("/api/audit")
            assert response.status_code == 200
            assert response.json()["deleted"] == 50

    def test_delete_position_found(self, client):
        with patch("trading_system.api.app.storage") as mock_storage:
            mock_storage.delete_position.return_value = True
            mock_storage.audit = MagicMock()
            response = client.delete("/api/positions/1")
            assert response.status_code == 200
            assert response.json()["deleted"] is True

    def test_delete_position_not_found(self, client):
        with patch("trading_system.api.app.storage") as mock_storage:
            mock_storage.delete_position.return_value = False
            response = client.delete("/api/positions/999")
            assert response.status_code == 404

    def test_delete_ai_weights(self, client):
        with patch("trading_system.api.app.storage") as mock_storage:
            mock_storage.delete_ai_weights.return_value = 3
            mock_storage.audit = MagicMock()
            response = client.delete("/api/ai/weights")
            assert response.status_code == 200
            assert response.json()["deleted"] == 3

    def test_delete_equity_snapshots(self, client):
        with patch("trading_system.api.app.storage") as mock_storage:
            mock_storage.delete_equity_snapshots.return_value = 30
            mock_storage.audit = MagicMock()
            response = client.delete("/api/performance/snapshots")
            assert response.status_code == 200
            assert response.json()["deleted"] == 30

    def test_delete_daily_risk_metrics(self, client):
        with patch("trading_system.api.app.storage") as mock_storage:
            mock_storage.delete_daily_risk_metrics.return_value = 15
            mock_storage.audit = MagicMock()
            response = client.delete("/api/risk/daily")
            assert response.status_code == 200
            assert response.json()["deleted"] == 15

    def test_delete_relationships(self, client):
        with patch("trading_system.api.app.storage") as mock_storage:
            mock_storage.delete_relationships.return_value = 8
            mock_storage.audit = MagicMock()
            response = client.delete("/api/relationships")
            assert response.status_code == 200
            assert response.json()["deleted"] == 8

    def test_delete_corporate_actions(self, client):
        with patch("trading_system.api.app.storage") as mock_storage:
            mock_storage.delete_corporate_actions.return_value = 4
            mock_storage.audit = MagicMock()
            response = client.delete("/api/corporate-actions/TEST.JK")
            assert response.status_code == 200
            assert response.json()["deleted"] == 4

    def test_delete_news(self, client):
        with patch("trading_system.api.app.storage") as mock_storage:
            mock_storage.delete_news.return_value = 20
            mock_storage.audit = MagicMock()
            response = client.delete("/api/news")
            assert response.status_code == 200
            assert response.json()["deleted"] == 20
