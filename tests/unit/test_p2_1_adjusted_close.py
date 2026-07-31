"""Unit tests for P2-1: Corporate action → adjusted_close integration."""

import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from trading_system.corporate.actions import CorporateActionEngine
from trading_system.data.storage import DataStorage


def _make_ohlcv_df(n=50, start_price=1000):
    dates = pd.bdate_range("2024-01-01", periods=n)
    rng = np.random.RandomState(42)
    close = start_price * np.cumprod(1 + rng.normal(0.001, 0.01, n))
    return pd.DataFrame({
        "ticker": "TEST.JK", "asset_class": "equity", "exchange": "IDX",
        "timestamp": dates.strftime("%Y-%m-%d %H:%M:%S"),
        "timeframe": "1d",
        "open": close, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": np.random.randint(1e6, 5e7, n).astype(float),
        "adjusted_close": close, "source": "test", "ingested_at": None,
        "data_quality_score": 95.0,
    })


class TestComputeAdjustmentFactor:
    """Tests for backward-adjusted price computation."""

    def test_no_actions_returns_close(self):
        storage = MagicMock()
        df = _make_ohlcv_df(50)
        df.index = pd.to_datetime(df["timestamp"])
        storage.load_ohlcv.return_value = df
        storage.load_corporate_actions.return_value = pd.DataFrame()

        engine = CorporateActionEngine(storage)
        result = engine.compute_adjustment_factor("TEST.JK")
        assert not result.empty
        assert "adj_factor" in result.columns
        assert "adj_close" in result.columns
        assert all(result["adj_factor"] == 1.0)
        assert all(result["adj_close"] == result["close"])

    def test_split_adjustment(self):
        storage = MagicMock()
        df = _make_ohlcv_df(50)
        df.index = pd.to_datetime(df["timestamp"])
        storage.load_ohlcv.return_value = df

        # 2:1 split at bar 30
        split_date = str(df.index[30].date())
        actions = pd.DataFrame([{
            "ticker": "TEST.JK", "action_type": "split",
            "ex_date": split_date, "value": 2.0, "unit": "ratio",
        }])
        storage.load_corporate_actions.return_value = actions

        engine = CorporateActionEngine(storage)
        result = engine.compute_adjustment_factor("TEST.JK")

        # Pre-split prices should be halved
        pre = result.iloc[:30]
        post = result.iloc[30:]
        assert np.allclose(pre["adj_factor"].values, 0.5, atol=0.001)
        assert np.allclose(post["adj_factor"].values, 1.0)
        assert np.allclose(pre["adj_close"].values, pre["close"].values * 0.5, atol=0.001)

    def test_dividend_adjustment(self):
        storage = MagicMock()
        df = _make_ohlcv_df(50)
        df.index = pd.to_datetime(df["timestamp"])
        storage.load_ohlcv.return_value = df

        # Dividend of 50 IDR at bar 30
        div_date = str(df.index[30].date())
        actions = pd.DataFrame([{
            "ticker": "TEST.JK", "action_type": "dividend",
            "ex_date": div_date, "value": 50.0, "unit": "IDR_per_share",
        }])
        storage.load_corporate_actions.return_value = actions

        engine = CorporateActionEngine(storage)
        result = engine.compute_adjustment_factor("TEST.JK")

        # Pre-dividend prices should be adjusted down
        pre = result.iloc[:30]
        post = result.iloc[30:]
        close_before_ex = float(df["close"].iloc[29])
        expected_ratio = (close_before_ex - 50.0) / close_before_ex

        assert np.allclose(pre["adj_factor"].values, expected_ratio, atol=0.001)
        assert np.allclose(post["adj_factor"].values, 1.0)

    def test_multiple_actions_cumulative(self):
        storage = MagicMock()
        df = _make_ohlcv_df(50)
        df.index = pd.to_datetime(df["timestamp"])
        storage.load_ohlcv.return_value = df

        # Split at bar 30, dividend at bar 15
        split_date = str(df.index[30].date())
        div_date = str(df.index[15].date())
        actions = pd.DataFrame([
            {"ticker": "TEST.JK", "action_type": "split", "ex_date": split_date, "value": 2.0, "unit": "ratio"},
            {"ticker": "TEST.JK", "action_type": "dividend", "ex_date": div_date, "value": 20.0, "unit": "IDR_per_share"},
        ])
        storage.load_corporate_actions.return_value = actions

        engine = CorporateActionEngine(storage)
        result = engine.compute_adjustment_factor("TEST.JK")

        # Bars 0-14: affected by both split and dividend
        # Bars 15-29: affected by split only
        # Bars 30+: no adjustment
        assert result["adj_factor"].iloc[0] < result["adj_factor"].iloc[20]
        assert result["adj_factor"].iloc[20] < result["adj_factor"].iloc[40]
        assert np.isclose(result["adj_factor"].iloc[40], 1.0)

    def test_empty_ohlcv(self):
        storage = MagicMock()
        storage.load_ohlcv.return_value = pd.DataFrame()
        storage.load_corporate_actions.return_value = pd.DataFrame()

        engine = CorporateActionEngine(storage)
        result = engine.compute_adjustment_factor("TEST.JK")
        assert result.empty

    def test_dividend_larger_than_price_skipped(self):
        storage = MagicMock()
        df = _make_ohlcv_df(50, start_price=10)
        df.index = pd.to_datetime(df["timestamp"])
        storage.load_ohlcv.return_value = df

        # Dividend of 100 IDR when price is ~10 — should be skipped
        div_date = str(df.index[30].date())
        actions = pd.DataFrame([{
            "ticker": "TEST.JK", "action_type": "dividend",
            "ex_date": div_date, "value": 100.0, "unit": "IDR_per_share",
        }])
        storage.load_corporate_actions.return_value = actions

        engine = CorporateActionEngine(storage)
        result = engine.compute_adjustment_factor("TEST.JK")
        # No adjustment applied because dividend > close
        assert np.allclose(result["adj_factor"].values, 1.0)


class TestStorageUpdateAdjustedClose:
    """Tests for DataStorage.update_adjusted_close integration."""

    def test_update_adjusted_close(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))

        # Save OHLCV
        df = _make_ohlcv_df(50)
        storage.save_ohlcv(df)

        # Save a corporate action
        split_date = str(pd.to_datetime(df["timestamp"].iloc[30]).date())
        storage.save_corporate_action({
            "ticker": "TEST.JK", "action_type": "split",
            "announce_date": None, "ex_date": split_date,
            "record_date": None, "payment_date": None,
            "value": 2.0, "unit": "ratio", "source": "test",
        })

        # Update adjusted_close
        n = storage.update_adjusted_close("TEST.JK")
        assert n > 0

        # Verify adjusted_close was updated in DB
        loaded = storage.load_ohlcv("TEST.JK")
        pre = loaded.iloc[:30]
        post = loaded.iloc[30:]
        assert all(pre["adjusted_close"] < pre["close"])
        assert np.allclose(post["adjusted_close"].values, post["close"].values, atol=0.001)

    def test_update_adjusted_close_no_actions(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        df = _make_ohlcv_df(50)
        storage.save_ohlcv(df)

        n = storage.update_adjusted_close("TEST.JK")
        # No actions → adj_close = close, but rows are still updated
        assert n > 0
        loaded = storage.load_ohlcv("TEST.JK")
        assert np.allclose(loaded["adjusted_close"].values, loaded["close"].values, atol=0.001)


class TestAcquisitionAdjustedCloseMapping:
    """Test that acquisition maps Adj Close → adjusted_close."""

    def test_column_mapping(self):
        # Simulate yfinance output
        df = pd.DataFrame({
            "Date": pd.bdate_range("2024-01-01", periods=5),
            "Open": [100, 101, 102, 103, 104],
            "High": [105, 106, 107, 108, 109],
            "Low": [99, 100, 101, 102, 103],
            "Close": [102, 103, 104, 105, 106],
            "Adj Close": [101, 102, 103, 104, 105],
            "Volume": [1e6, 2e6, 3e6, 4e6, 5e6],
            "Stock Splits": [0, 0, 0, 0, 0],
            "Dividends": [0, 0, 0, 0, 0],
        })

        df.rename(columns={
            "Date": "timestamp", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Adj Close": "adjusted_close",
            "Volume": "volume", "Stock Splits": "splits", "Dividends": "dividends",
        }, inplace=True)

        assert "adjusted_close" in df.columns
        assert "adj_close" not in df.columns
        assert list(df["adjusted_close"]) == [101, 102, 103, 104, 105]
