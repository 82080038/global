"""Shared test fixtures for unit tests."""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


@pytest.fixture
def mock_ohlcv_df():
    """Generate a realistic OHLCV DataFrame for testing (250 trading days)."""
    np.random.seed(42)
    n = 250
    dates = pd.date_range(start="2024-01-01", periods=n, freq="B")

    base_price = 8000
    returns = np.random.normal(0.0005, 0.015, n)
    close = base_price * np.cumprod(1 + returns)

    high = close * (1 + np.abs(np.random.normal(0, 0.01, n)))
    low = close * (1 - np.abs(np.random.normal(0, 0.01, n)))
    open_ = np.roll(close, 1)
    open_[0] = base_price
    volume = np.random.randint(1_000_000, 50_000_000, n).astype(float)

    df = pd.DataFrame({
        "ticker": "TEST.JK",
        "asset_class": "equity",
        "exchange": "IDX",
        "timestamp": dates.strftime("%Y-%m-%d"),
        "timeframe": "1d",
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "adjusted_close": close,
        "source": "test",
        "ingested_at": datetime.now().isoformat(),
        "data_quality_score": None,
    })
    return df


@pytest.fixture
def mock_ohlcv_indexed_df(mock_ohlcv_df):
    """OHLCV DataFrame with timestamp index (as stored in DB)."""
    df = mock_ohlcv_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df.set_index("timestamp", inplace=True)
    return df


@pytest.fixture
def mock_storage(mock_ohlcv_indexed_df):
    """Mock DataStorage that returns test OHLCV data."""
    storage = MagicMock()
    storage.load_ohlcv.return_value = mock_ohlcv_indexed_df
    storage.load_scores.return_value = pd.DataFrame()
    storage.save_score = MagicMock()
    storage.save_ohlcv = MagicMock(return_value=len(mock_ohlcv_indexed_df))
    storage.audit = MagicMock()
    storage.get_ai_weights.return_value = None
    storage.list_tickers.return_value = []
    storage.get_open_position.return_value = None
    return storage
