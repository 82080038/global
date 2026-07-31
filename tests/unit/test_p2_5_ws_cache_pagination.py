"""Unit tests for P2-5: WS broadcast cache + pagination."""

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client with mocked storage."""
    with patch("trading_system.api.app.storage", MagicMock()):
        from trading_system.api.app import app
        yield TestClient(app)


class TestPagination:
    """Tests for pagination on list endpoints."""

    def test_tickers_pagination(self, client):
        with patch("trading_system.api.app.storage") as mock_storage:
            mock_storage.list_tickers.return_value = [f"STOCK{i}.JK" for i in range(250)]
            resp = client.get("/api/tickers?page=1&limit=100")
            assert resp.status_code == 200
            data = resp.json()
            assert data["count"] == 250
            assert data["page"] == 1
            assert data["limit"] == 100
            assert data["pages"] == 3
            assert len(data["tickers"]) == 100

    def test_tickers_pagination_page2(self, client):
        with patch("trading_system.api.app.storage") as mock_storage:
            mock_storage.list_tickers.return_value = [f"STOCK{i}.JK" for i in range(250)]
            resp = client.get("/api/tickers?page=2&limit=100")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["tickers"]) == 100
            assert data["tickers"][0] == "STOCK100.JK"

    def test_tickers_pagination_last_page(self, client):
        with patch("trading_system.api.app.storage") as mock_storage:
            mock_storage.list_tickers.return_value = [f"STOCK{i}.JK" for i in range(250)]
            resp = client.get("/api/tickers?page=3&limit=100")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["tickers"]) == 50

    def test_ohlcv_pagination(self, client):
        import pandas as pd
        dates = pd.bdate_range("2024-01-01", periods=1000)
        df = pd.DataFrame({
            "open": range(1000), "high": range(1000),
            "low": range(1000), "close": range(1000),
            "volume": range(1000), "adjusted_close": range(1000),
        }, index=dates)
        with patch("trading_system.api.app.storage") as mock_storage:
            mock_storage.load_ohlcv.return_value = df
            resp = client.get("/api/data/ohlcv?ticker=TEST.JK&page=1&limit=100")
            assert resp.status_code == 200
            data = resp.json()
            assert data["count"] == 1000
            assert data["page"] == 1
            assert data["pages"] == 10
            assert len(data["data"]) == 100

    def test_watchlist_all_pagination(self, client):
        with patch("trading_system.api.app.storage") as mock_storage:
            mock_storage.get_watchlist.return_value = [
                {"ticker": f"S{i}.JK", "is_favorite": True} for i in range(150)
            ]
            resp = client.get("/api/watchlist/all?page=2&limit=50")
            assert resp.status_code == 200
            data = resp.json()
            assert data["count"] == 150
            assert data["page"] == 2
            assert len(data["items"]) == 50


class TestEngineStatusCache:
    """Tests for engine status caching (P2-5)."""

    def test_cache_returns_same_object_within_ttl(self):
        """Within TTL, _get_engines_status should return cached result."""
        import trading_system.api.app as app_module

        app_module._engines_status_cache = None
        app_module._engines_status_cache_ts = 0

        with patch.object(app_module, "_build_engines_status", return_value={"test": 1}) as mock_build:
            r1 = app_module._get_engines_status()
            r2 = app_module._get_engines_status()
            assert r1 is r2
            assert mock_build.call_count == 1

        app_module._engines_status_cache = None
        app_module._engines_status_cache_ts = 0

    def test_cache_rebuilds_after_ttl(self):
        """After TTL expires, _get_engines_status should rebuild."""
        import trading_system.api.app as app_module

        app_module._engines_status_cache = None
        app_module._engines_status_cache_ts = 0

        with patch.object(app_module, "_build_engines_status", side_effect=[{"v": 1}, {"v": 2}]) as mock_build:
            r1 = app_module._get_engines_status()
            app_module._engines_status_cache_ts -= 10
            r2 = app_module._get_engines_status()
            assert r1 != r2
            assert mock_build.call_count == 2

        app_module._engines_status_cache = None
        app_module._engines_status_cache_ts = 0
