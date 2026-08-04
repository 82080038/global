"""Unit tests for macro data adapters (FRED, BPS, Bank Indonesia)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from trading_system.data.adaptive_rate_limiter import AdaptiveRateLimiter
from trading_system.data.macro_adapters import (
    BI_ENDPOINTS,
    BI_SERIES,
    BPS_SERIES,
    FRED_SERIES,
    BPSAdapter,
    BIAdapter,
    FREDAdapter,
)


# ---------------------------------------------------------------------------
# FRED Adapter Tests
# ---------------------------------------------------------------------------


class TestFREDAdapter:
    def test_init_without_api_key(self):
        """Adapter initializes with empty key when env var not set."""
        with patch.dict(os.environ, {}, clear=True):
            adapter = FREDAdapter(api_key="")
            assert adapter.api_key == ""
            assert adapter.name == "fred"

    def test_init_with_api_key(self):
        adapter = FREDAdapter(api_key="test_key_123")
        assert adapter.api_key == "test_key_123"

    def test_fetch_series_without_api_key_returns_error(self):
        adapter = FREDAdapter(api_key="", storage=MagicMock())
        result = adapter.fetch_series("DGS10")
        assert result["status"] == "error"
        assert "FRED_API_KEY" in result["message"]

    def test_fetch_series_success(self):
        """Mock the HTTP call and verify data is saved to macro_data."""
        mock_storage = MagicMock()
        mock_rl = MagicMock()
        mock_rl.execute.return_value = MagicMock(
            data=pd.DataFrame({
                "date": ["2025-01-01", "2025-01-02", "2025-01-03"],
                "value": [4.5, 4.6, 4.55],
            }),
            error=None,
            attempts=1,
        )

        adapter = FREDAdapter(api_key="test_key", storage=mock_storage, rate_limiter=mock_rl)
        result = adapter.fetch_series("DGS10")

        assert result["status"] == "ok"
        assert "3 rows" in result["message"]
        assert mock_storage.save_macro_data.call_count == 3
        mock_storage.update_source_health.assert_called_with("fred", "ok", success=True)

    def test_fetch_series_handles_missing_values(self):
        """FRED returns '.' for missing values — should be skipped."""
        mock_storage = MagicMock()
        mock_rl = MagicMock()
        mock_rl.execute.return_value = MagicMock(
            data=pd.DataFrame({
                "date": ["2025-01-01", "2025-01-02"],
                "value": [4.5, float("nan")],
            }),
            error=None,
            attempts=1,
        )

        adapter = FREDAdapter(api_key="test_key", storage=mock_storage, rate_limiter=mock_rl)
        result = adapter.fetch_series("DGS10")

        assert result["status"] == "ok"
        assert "1 rows" in result["message"]
        assert mock_storage.save_macro_data.call_count == 1

    def test_fetch_series_api_error(self):
        mock_storage = MagicMock()
        mock_rl = MagicMock()
        mock_rl.execute.return_value = MagicMock(
            data=None, error="HTTP 403: Forbidden", attempts=3,
        )

        adapter = FREDAdapter(api_key="test_key", storage=mock_storage, rate_limiter=mock_rl)
        result = adapter.fetch_series("DGS10")

        assert result["status"] == "error"
        assert "HTTP 403" in result["message"]
        mock_storage.update_source_health.assert_called_with("fred", "down", success=False)

    def test_fetch_series_empty_response(self):
        mock_storage = MagicMock()
        mock_rl = MagicMock()
        mock_rl.execute.return_value = MagicMock(
            data=pd.DataFrame(), error=None, attempts=1,
        )

        adapter = FREDAdapter(api_key="test_key", storage=mock_storage, rate_limiter=mock_rl)
        result = adapter.fetch_series("UNKNOWN_SERIES")

        assert result["status"] == "empty"

    def test_fetch_all_iterates_all_series(self):
        mock_storage = MagicMock()
        mock_rl = MagicMock()
        mock_rl.execute.return_value = MagicMock(
            data=pd.DataFrame(), error=None, attempts=1,
        )

        adapter = FREDAdapter(api_key="test_key", storage=mock_storage, rate_limiter=mock_rl)
        results = adapter.fetch_all()

        assert len(results) == len(FRED_SERIES)
        for sid in FRED_SERIES:
            assert sid in results

    def test_fetch_series_custom_id_not_in_preset(self):
        """Custom series IDs not in FRED_SERIES should still work."""
        mock_storage = MagicMock()
        mock_rl = MagicMock()
        mock_rl.execute.return_value = MagicMock(
            data=pd.DataFrame({"date": ["2025-01-01"], "value": [1.0]}),
            error=None,
            attempts=1,
        )

        adapter = FREDAdapter(api_key="test_key", storage=mock_storage, rate_limiter=mock_rl)
        result = adapter.fetch_series("CUSTOM_SERIES")

        assert result["status"] == "ok"

    def test_fred_series_preset_contains_key_indicators(self):
        assert "DGS10" in FRED_SERIES  # US 10Y Treasury
        assert "VIXCLS" in FRED_SERIES  # VIX
        assert "DCOILWTICO" in FRED_SERIES  # WTI Oil
        assert "FEDFUNDS" in FRED_SERIES  # Fed Funds Rate


# ---------------------------------------------------------------------------
# BPS Adapter Tests
# ---------------------------------------------------------------------------


class TestBPSAdapter:
    def test_init_without_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            adapter = BPSAdapter(api_key="")
            assert adapter.api_key == ""
            assert adapter.name == "bps"

    def test_fetch_series_without_api_key_returns_error(self):
        adapter = BPSAdapter(api_key="", storage=MagicMock())
        result = adapter.fetch_series("gdp_growth", "1234")
        assert result["status"] == "error"
        assert "BPS_API_KEY" in result["message"]

    def test_fetch_series_success(self):
        mock_storage = MagicMock()
        mock_rl = MagicMock()
        mock_rl.execute.return_value = MagicMock(
            data=pd.DataFrame({
                "date": ["2025Q1", "2025Q2"],
                "value": [5.0, 5.1],
            }),
            error=None,
            attempts=1,
        )

        adapter = BPSAdapter(api_key="test_key", storage=mock_storage, rate_limiter=mock_rl)
        result = adapter.fetch_series("gdp_growth", "var_123")

        assert result["status"] == "ok"
        assert "2 rows" in result["message"]
        assert mock_storage.save_macro_data.call_count == 2

    def test_fetch_series_api_error(self):
        mock_storage = MagicMock()
        mock_rl = MagicMock()
        mock_rl.execute.return_value = MagicMock(
            data=None, error="HTTP 500", attempts=3,
        )

        adapter = BPSAdapter(api_key="test_key", storage=mock_storage, rate_limiter=mock_rl)
        result = adapter.fetch_series("inflation_yoy", "var_456")

        assert result["status"] == "error"
        mock_storage.update_source_health.assert_called_with("bps", "down", success=False)

    def test_fetch_series_empty(self):
        mock_storage = MagicMock()
        mock_rl = MagicMock()
        mock_rl.execute.return_value = MagicMock(
            data=pd.DataFrame(), error=None, attempts=1,
        )

        adapter = BPSAdapter(api_key="test_key", storage=mock_storage, rate_limiter=mock_rl)
        result = adapter.fetch_series("trade_balance", "var_789")

        assert result["status"] == "empty"

    def test_fetch_all_without_var_ids_skips(self):
        mock_storage = MagicMock()
        mock_rl = MagicMock()

        adapter = BPSAdapter(api_key="test_key", storage=mock_storage, rate_limiter=mock_rl)
        results = adapter.fetch_all()

        assert len(results) == len(BPS_SERIES)
        for sk in BPS_SERIES:
            assert results[sk]["status"] == "skipped"

    def test_fetch_all_with_var_ids(self):
        mock_storage = MagicMock()
        mock_rl = MagicMock()
        mock_rl.execute.return_value = MagicMock(
            data=pd.DataFrame({"date": ["2025-01"], "value": [3.2]}),
            error=None,
            attempts=1,
        )

        adapter = BPSAdapter(api_key="test_key", storage=mock_storage, rate_limiter=mock_rl)
        results = adapter.fetch_all({"gdp_growth": "var_123", "inflation_yoy": "var_456"})

        assert results["gdp_growth"]["status"] == "ok"
        assert results["inflation_yoy"]["status"] == "ok"

    def test_bps_series_preset_contains_key_indicators(self):
        assert "gdp_growth" in BPS_SERIES
        assert "inflation_yoy" in BPS_SERIES
        assert "trade_balance" in BPS_SERIES
        assert "manufacturing_pmi" in BPS_SERIES

    def test_build_params(self):
        adapter = BPSAdapter(api_key="test_key", storage=MagicMock())
        params = adapter._build_params(model="data", var="123", th="2020-2025")
        assert params["model"] == "data"
        assert params["var"] == "123"
        assert params["key"] == "test_key"
        assert params["domain"] == "0000"


# ---------------------------------------------------------------------------
# Bank Indonesia Adapter Tests
# ---------------------------------------------------------------------------


class TestBIAdapter:
    def test_init(self):
        adapter = BIAdapter(storage=MagicMock())
        assert adapter.name == "bank_indonesia"
        assert adapter.api_key is None  # BI doesn't need API key

    def test_fetch_series_unknown_key(self):
        adapter = BIAdapter(storage=MagicMock())
        result = adapter.fetch_series("unknown_series")
        assert result["status"] == "error"
        assert "Unknown series" in result["message"]

    def test_fetch_series_no_endpoint(self):
        """Series in BI_SERIES but not in BI_ENDPOINTS should return error."""
        adapter = BIAdapter(storage=MagicMock())
        # m0 is in BI_SERIES but not in BI_ENDPOINTS
        result = adapter.fetch_series("m0")
        assert result["status"] == "error"
        assert "No BI endpoint" in result["message"]

    def test_fetch_series_success(self):
        mock_storage = MagicMock()
        mock_rl = MagicMock()
        mock_rl.execute.return_value = MagicMock(
            data=pd.DataFrame({
                "date": ["2025-01-15", "2025-02-15"],
                "value": [6.0, 6.0],
            }),
            error=None,
            attempts=1,
        )

        adapter = BIAdapter(storage=mock_storage, rate_limiter=mock_rl)
        result = adapter.fetch_series("bi_rate")

        assert result["status"] == "ok"
        assert "2 rows" in result["message"]
        assert mock_storage.save_macro_data.call_count == 2
        mock_storage.update_source_health.assert_called_with("bank_indonesia", "ok", success=True)

    def test_fetch_series_api_error(self):
        mock_storage = MagicMock()
        mock_rl = MagicMock()
        mock_rl.execute.return_value = MagicMock(
            data=None, error="Connection timeout", attempts=3,
        )

        adapter = BIAdapter(storage=mock_storage, rate_limiter=mock_rl)
        result = adapter.fetch_series("usd_idr_jisdor")

        assert result["status"] == "error"
        assert "Connection timeout" in result["message"]
        mock_storage.update_source_health.assert_called_with("bank_indonesia", "down", success=False)

    def test_fetch_series_empty(self):
        mock_storage = MagicMock()
        mock_rl = MagicMock()
        mock_rl.execute.return_value = MagicMock(
            data=pd.DataFrame(), error=None, attempts=1,
        )

        adapter = BIAdapter(storage=mock_storage, rate_limiter=mock_rl)
        result = adapter.fetch_series("bi_rate")

        assert result["status"] == "empty"

    def test_fetch_all_iterates_endpoints(self):
        mock_storage = MagicMock()
        mock_rl = MagicMock()
        mock_rl.execute.return_value = MagicMock(
            data=pd.DataFrame(), error=None, attempts=1,
        )

        adapter = BIAdapter(storage=mock_storage, rate_limiter=mock_rl)
        results = adapter.fetch_all()

        assert len(results) == len(BI_ENDPOINTS)
        for sk in BI_ENDPOINTS:
            assert sk in results

    def test_bi_series_preset_contains_key_indicators(self):
        assert "bi_rate" in BI_SERIES
        assert "usd_idr_jisdor" in BI_SERIES
        assert "m2" in BI_SERIES
        assert "foreign_reserves" in BI_SERIES
        assert "gov_bond_10y" in BI_SERIES

    def test_bi_endpoints_subset_of_series(self):
        """All endpoints should have corresponding series metadata."""
        for sk in BI_ENDPOINTS:
            assert sk in BI_SERIES, f"Endpoint '{sk}' missing from BI_SERIES"


# ---------------------------------------------------------------------------
# Rate Limiter Preset Tests
# ---------------------------------------------------------------------------


class TestRateLimiterPresets:
    def test_for_fred_preset(self):
        rl = AdaptiveRateLimiter.for_fred()
        assert rl.min_delay == 0.5
        assert rl.max_requests == 120
        assert rl.window_seconds == 60

    def test_for_bps_preset(self):
        rl = AdaptiveRateLimiter.for_bps()
        assert rl.min_delay == 1.0
        assert rl.max_requests == 60

    def test_for_bi_preset(self):
        rl = AdaptiveRateLimiter.for_bi()
        assert rl.min_delay == 2.0
        assert rl.max_requests == 30
        assert rl.circuit_reset_seconds == 120
