"""Tests for PortfolioEngine — position management and order generation."""

import pandas as pd
from unittest.mock import MagicMock

from trading_system.portfolio.engine import PortfolioEngine


def test_portfolio_engine_name():
    engine = PortfolioEngine(storage=MagicMock())
    assert engine.name == "portfolio"


def test_current_positions_empty():
    storage = MagicMock()
    storage.get_all_open_positions.return_value = []
    engine = PortfolioEngine(storage=storage, cash=500_000_000)
    df = engine.current_positions()
    assert "CASH" in df["ticker"].values
    assert df.iloc[0]["quantity"] == 500_000_000


def test_current_positions_with_data():
    storage = MagicMock()
    storage.get_all_open_positions.return_value = [
        {"ticker": "BBCA.JK", "quantity": 1000, "avg_entry_price": 9000},
        {"ticker": "TLKM.JK", "quantity": 500, "avg_entry_price": 3500},
    ]
    engine = PortfolioEngine(storage=storage)
    df = engine.current_positions()
    assert len(df) == 2
    assert "avg_price" in df.columns
    assert df.iloc[0]["ticker"] == "BBCA.JK"


def test_get_exposure_empty():
    storage = MagicMock()
    storage.get_all_open_positions.return_value = []
    engine = PortfolioEngine(storage=storage, cash=1_000_000_000)
    exposure = engine.get_exposure()
    assert exposure["invested"] == 0
    assert exposure["exposure_pct"] == 0
    assert exposure["position_count"] == 0


def test_get_exposure_with_positions():
    storage = MagicMock()
    storage.get_all_open_positions.return_value = [
        {"ticker": "BBCA.JK", "quantity": 1000, "avg_entry_price": 9000},
    ]
    engine = PortfolioEngine(storage=storage, cash=1_000_000_000)
    exposure = engine.get_exposure()
    assert exposure["invested"] == 9_000_000
    assert exposure["position_count"] == 1
    assert exposure["exposure_pct"] > 0


def test_generate_buy_order():
    storage = MagicMock()
    storage.get_open_position.return_value = None
    engine = PortfolioEngine(storage=storage, cash=1_000_000_000)
    orders = engine.generate_orders({
        "action": "BUY",
        "ticker": "BBCA.JK",
        "position_size": 0.05,
        "entry_price_range": [8900, 9100],
    })
    assert len(orders) == 1
    assert orders[0]["action"] == "BUY"
    assert orders[0]["shares"] > 0


def test_generate_buy_skip_if_existing_position():
    storage = MagicMock()
    storage.get_open_position.return_value = {"id": 1, "ticker": "BBCA.JK", "quantity": 500}
    engine = PortfolioEngine(storage=storage)
    orders = engine.generate_orders({
        "action": "BUY",
        "ticker": "BBCA.JK",
        "position_size": 0.05,
        "entry_price_range": [8900, 9100],
    })
    assert len(orders) == 0


def test_generate_sell_order():
    storage = MagicMock()
    storage.get_open_position.return_value = {"id": 1, "ticker": "BBCA.JK", "quantity": 1000}
    engine = PortfolioEngine(storage=storage)
    orders = engine.generate_orders({
        "action": "SELL",
        "ticker": "BBCA.JK",
        "entry_price_range": [9500, 9600],
    })
    assert len(orders) == 1
    assert orders[0]["action"] == "SELL"
    assert orders[0]["shares"] == 1000


def test_generate_sell_no_position():
    storage = MagicMock()
    storage.get_open_position.return_value = None
    engine = PortfolioEngine(storage=storage)
    orders = engine.generate_orders({
        "action": "SELL",
        "ticker": "BBCA.JK",
        "entry_price_range": [9500, 9600],
    })
    assert len(orders) == 0


def test_generate_orders_hold_action():
    engine = PortfolioEngine(storage=MagicMock())
    orders = engine.generate_orders({
        "action": "HOLD",
        "ticker": "BBCA.JK",
    })
    assert len(orders) == 0
