"""Tests for PaperTradingEngine — simulated order execution."""

from unittest.mock import MagicMock

from trading_system.paper_trading.engine import PaperTradingEngine


def test_paper_trading_engine_name():
    engine = PaperTradingEngine(storage=MagicMock())
    assert engine.name == "paper_trading"


def test_paper_trade_no_data():
    storage = MagicMock()
    storage.load_ohlcv.return_value = MagicMock(empty=True)
    engine = PaperTradingEngine(storage=storage)
    result = engine.simulate("BBCA.JK")
    assert result["status"] == "error"
