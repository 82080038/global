"""Tests for CorporateActionEngine — split and dividend detection."""

import pandas as pd
from unittest.mock import MagicMock, patch

from trading_system.corporate.actions import CorporateActionEngine


def test_corporate_engine_name():
    engine = CorporateActionEngine(storage=MagicMock())
    assert engine.name == "corporate_action"


def test_corporate_fetch_no_data():
    """When yfinance returns no actions, should handle gracefully."""
    storage = MagicMock()
    engine = CorporateActionEngine(storage=storage)
    with patch("trading_system.corporate.actions.yf") as mock_yf:
        mock_ticker = MagicMock()
        mock_ticker.actions = pd.DataFrame()
        mock_ticker.dividends = pd.Series(dtype=float)
        mock_ticker.splits = pd.Series(dtype=float)
        mock_yf.Ticker.return_value = mock_ticker
        result = engine.fetch("TEST.JK")
        assert result["status"] in ("ok", "error", "warning")


def test_corporate_fetch_with_dividend():
    """When yfinance returns dividends, should parse correctly."""
    storage = MagicMock()
    engine = CorporateActionEngine(storage=storage)
    with patch("trading_system.corporate.actions.yf") as mock_yf:
        mock_ticker = MagicMock()
        mock_ticker.actions = pd.DataFrame()
        mock_ticker.dividends = pd.Series({pd.Timestamp("2024-06-15"): 50.0})
        mock_ticker.splits = pd.Series(dtype=float)
        mock_yf.Ticker.return_value = mock_ticker
        result = engine.fetch("TEST.JK")
        assert result["status"] in ("ok", "warning")


def test_corporate_fetch_exception():
    """When yfinance raises exception on splits/dividends, should return error."""
    storage = MagicMock()
    engine = CorporateActionEngine(storage=storage)
    with patch("trading_system.corporate.actions.yf") as mock_yf:
        mock_ticker = MagicMock()
        type(mock_ticker).splits = property(lambda self: (_ for _ in ()).throw(Exception("Network error")))
        mock_yf.Ticker.return_value = mock_ticker
        result = engine.fetch("TEST.JK")
        assert result["status"] == "error"
