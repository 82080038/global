"""Unit tests for DataSourceAdapter and YahooFinanceAdapter (§4.1)."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from trading_system.data.acquisition import DataSourceAdapter, YahooFinanceAdapter, normalize_ohlcv


class TestDataSourceAdapter:
    """Tests for the abstract DataSourceAdapter interface (§4.1)."""

    def test_cannot_instantiate_abstract_class(self):
        """DataSourceAdapter is abstract and cannot be instantiated directly."""
        with pytest.raises(TypeError):
            DataSourceAdapter()

    def test_yahoo_finance_is_data_source_adapter(self):
        """YahooFinanceAdapter must inherit from DataSourceAdapter."""
        assert issubclass(YahooFinanceAdapter, DataSourceAdapter)

    def test_yahoo_finance_has_name(self):
        """Adapter must have a name attribute."""
        assert YahooFinanceAdapter.name == "yahoo_finance"

    def test_fetch_incremental_without_timestamp_falls_back_to_full_fetch(self):
        """fetch_incremental with no last_timestamp should call fetch with 2y period."""
        adapter = YahooFinanceAdapter.__new__(YahooFinanceAdapter)
        adapter.storage = MagicMock()

        with patch.object(adapter, "fetch") as mock_fetch:
            mock_fetch.return_value = {"status": "ok", "records": pd.DataFrame(), "message": "test"}
            result = adapter.fetch_incremental("TEST.JK", last_timestamp=None)

            mock_fetch.assert_called_once_with("TEST.JK", period="2y", interval="1d")
            assert result["status"] == "ok"

    def test_fetch_incremental_recent_data_uses_short_period(self):
        """fetch_incremental with recent last_timestamp should use short period."""
        adapter = YahooFinanceAdapter.__new__(YahooFinanceAdapter)
        adapter.storage = MagicMock()

        # 1 day ago → should use "5d" period
        recent_ts = (datetime.now(UTC) - pd.Timedelta(days=1)).isoformat()

        with patch.object(adapter, "fetch") as mock_fetch:
            mock_fetch.return_value = {"status": "ok", "records": pd.DataFrame(), "message": "test"}
            adapter.fetch_incremental("TEST.JK", last_timestamp=recent_ts)

            call_args = mock_fetch.call_args
            assert call_args.kwargs["period"] == "5d"

    def test_fetch_incremental_old_data_uses_long_period(self):
        """fetch_incremental with old last_timestamp should use longer period."""
        adapter = YahooFinanceAdapter.__new__(YahooFinanceAdapter)
        adapter.storage = MagicMock()

        # 200 days ago → should use "1y" period
        old_ts = (datetime.now(UTC) - pd.Timedelta(days=200)).isoformat()

        with patch.object(adapter, "fetch") as mock_fetch:
            mock_fetch.return_value = {"status": "ok", "records": pd.DataFrame(), "message": "test"}
            adapter.fetch_incremental("TEST.JK", last_timestamp=old_ts)

            call_args = mock_fetch.call_args
            assert call_args.kwargs["period"] == "1y"


class TestNormalizeOHLCV:
    """Tests for normalize_ohlcv with adjusted_close support (§4.3)."""

    def test_normalize_with_adj_close(self):
        """normalize_ohlcv should use adj_close column when available."""
        df = pd.DataFrame({
            "ticker": ["TEST.JK"],
            "open": [100.0],
            "high": [105.0],
            "low": [99.0],
            "close": [102.0],
            "adj_close": [101.0],
            "volume": [1000000],
            "source": ["test"],
            "timestamp": ["2024-01-01"],
        })
        result = normalize_ohlcv(df)
        assert result["adjusted_close"].iloc[0] == 101.0

    def test_normalize_without_adj_close_falls_back_to_close(self):
        """normalize_ohlcv should fall back to close when adj_close is missing."""
        df = pd.DataFrame({
            "ticker": ["TEST.JK"],
            "open": [100.0],
            "high": [105.0],
            "low": [99.0],
            "close": [102.0],
            "volume": [1000000],
            "source": ["test"],
            "timestamp": ["2024-01-01"],
        })
        result = normalize_ohlcv(df)
        assert result["adjusted_close"].iloc[0] == 102.0
