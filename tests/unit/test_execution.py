"""Unit tests for AutomatedExecutionEngine."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from trading_system.data.storage import DataStorage
from trading_system.execution.automated import AutomatedExecutionEngine


@pytest.fixture
def temp_storage():
    """Create a temporary DataStorage with test data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_execution.db"
        storage = DataStorage(db_path=db_path)

        # Save test OHLCV data
        dates = pd.date_range("2024-01-01", periods=60, freq="D")
        df = pd.DataFrame({
            "ticker": ["TEST.JK"] * 60,
            "asset_class": ["stock"] * 60,
            "exchange": ["IDX"] * 60,
            "timestamp": [d.isoformat() for d in dates],
            "timeframe": ["1d"] * 60,
            "open": [100 + i * 0.5 for i in range(60)],
            "high": [105 + i * 0.5 for i in range(60)],
            "low": [95 + i * 0.5 for i in range(60)],
            "close": [102 + i * 0.5 for i in range(60)],
            "volume": [1_000_000 + i * 1000 for i in range(60)],
            "adjusted_close": [102 + i * 0.5 for i in range(60)],
            "source": ["test"] * 60,
            "ingested_at": [dates[0].isoformat()] * 60,
            "data_quality_score": [95.0] * 60,
        })
        storage.save_ohlcv(df)
        yield storage


class TestAutomatedExecutionEngine:

    def test_init_defaults(self, temp_storage):
        """Engine initializes with auto_trade disabled by default."""
        os.environ.pop("AUTO_TRADE_ENABLED", None)
        engine = AutomatedExecutionEngine(storage=temp_storage)
        assert engine.auto_trade_enabled is False
        assert engine.capital > 0

    def test_init_auto_trade_enabled(self, temp_storage):
        """Engine can be enabled via env var."""
        os.environ["AUTO_TRADE_ENABLED"] = "true"
        engine = AutomatedExecutionEngine(storage=temp_storage)
        assert engine.auto_trade_enabled is True
        os.environ.pop("AUTO_TRADE_ENABLED", None)

    def test_get_latest_price(self, temp_storage):
        """Latest price is retrieved from OHLCV."""
        engine = AutomatedExecutionEngine(storage=temp_storage)
        price = engine._get_latest_price("TEST.JK")
        assert price is not None
        assert price == pytest.approx(102 + 59 * 0.5, rel=0.01)

    def test_get_latest_price_no_data(self, temp_storage):
        """Returns None if no OHLCV data."""
        engine = AutomatedExecutionEngine(storage=temp_storage)
        price = engine._get_latest_price("NONEXIST.JK")
        assert price is None

    def test_get_atr(self, temp_storage):
        """ATR is computed from OHLCV data."""
        engine = AutomatedExecutionEngine(storage=temp_storage)
        atr = engine._get_atr("TEST.JK")
        assert atr > 0

    def test_compute_position_size(self, temp_storage):
        """Position size is computed and rounded to lots of 100."""
        engine = AutomatedExecutionEngine(storage=temp_storage)
        price = 130
        qty = engine._compute_position_size("TEST.JK", price)
        assert qty > 0
        assert qty % 100 == 0  # Rounded to lot

    def test_execute_buy_creates_position_and_order(self, temp_storage):
        """BUY creates a position and an order record."""
        engine = AutomatedExecutionEngine(storage=temp_storage)
        result = engine._execute_buy("TEST.JK", 100, 130.0, trigger="SIGNAL")
        assert result["status"] == "ok"
        assert result["action"] == "BUY"
        assert result["quantity"] == 100
        assert result["price"] == 130.0

        # Verify position created
        pos = temp_storage.get_open_position("TEST.JK")
        assert pos is not None
        assert pos["quantity"] == 100
        assert pos["avg_entry_price"] == 130.0
        assert pos["status"] == "OPEN"

        # Verify order saved
        orders = temp_storage.get_orders("TEST.JK")
        assert len(orders) == 1
        assert orders[0]["order_type"] == "BUY"
        assert orders[0]["quantity"] == 100

    def test_execute_sell_closes_position(self, temp_storage):
        """SELL closes the position and records realized PnL."""
        engine = AutomatedExecutionEngine(storage=temp_storage)

        # First buy
        engine._execute_buy("TEST.JK", 100, 100.0, trigger="SIGNAL")

        # Then sell at higher price
        pos = temp_storage.get_open_position("TEST.JK")
        result = engine._execute_sell("TEST.JK", 100, 120.0, trigger="SIGNAL", position=pos)

        assert result["status"] == "ok"
        assert result["action"] == "SELL"
        assert result["realized_pnl"] == pytest.approx(2000.0, rel=0.01)

        # Position should be closed
        pos_after = temp_storage.get_open_position("TEST.JK")
        assert pos_after is None

        # Two orders: buy + sell
        orders = temp_storage.get_orders("TEST.JK")
        assert len(orders) == 2

    def test_check_stop_loss_triggers_sell(self, temp_storage):
        """Stop loss triggers automatic sell."""
        engine = AutomatedExecutionEngine(storage=temp_storage)

        # Create position with tight stop loss
        pos_id = temp_storage.save_position("TEST.JK", 100, 130.0,
                                             stop_loss=125.0, take_profit=150.0)

        # Mock latest price below stop loss
        with patch.object(engine, "_get_latest_price", return_value=120.0):
            result = engine.check_stop_loss_take_profit("TEST.JK")

        assert result is not None
        assert result["action"] == "SELL"
        # Check trigger was recorded in order
        orders = temp_storage.get_orders("TEST.JK")
        sell_orders = [o for o in orders if o["order_type"] == "SELL"]
        assert len(sell_orders) >= 1
        assert sell_orders[0]["trigger"] == "STOP_LOSS"

    def test_check_take_profit_triggers_sell(self, temp_storage):
        """Take profit triggers automatic sell."""
        engine = AutomatedExecutionEngine(storage=temp_storage)

        # Create position with take profit
        temp_storage.save_position("TEST.JK", 100, 130.0,
                                    stop_loss=120.0, take_profit=140.0)

        with patch.object(engine, "_get_latest_price", return_value=145.0):
            result = engine.check_stop_loss_take_profit("TEST.JK")

        assert result is not None
        assert result["action"] == "SELL"

    def test_check_no_trigger_when_price_in_range(self, temp_storage):
        """No SL/TP trigger when price is within range."""
        engine = AutomatedExecutionEngine(storage=temp_storage)

        temp_storage.save_position("TEST.JK", 100, 130.0,
                                    stop_loss=120.0, take_profit=150.0)

        with patch.object(engine, "_get_latest_price", return_value=135.0):
            result = engine.check_stop_loss_take_profit("TEST.JK")

        assert result is None

    def test_check_no_position_returns_none(self, temp_storage):
        """No position means no SL/TP check needed."""
        engine = AutomatedExecutionEngine(storage=temp_storage)
        result = engine.check_stop_loss_take_profit("TEST.JK")
        assert result is None

    def test_trailing_stop_triggers(self, temp_storage):
        """Trailing stop triggers when price drops from highest."""
        engine = AutomatedExecutionEngine(storage=temp_storage)

        # Create position with trailing stop
        pos_id = temp_storage.save_position("TEST.JK", 100, 100.0,
                                    stop_loss=90.0, take_profit=200.0,
                                    trailing_stop_pct=0.05)

        # First update: price goes up to 120
        with patch.object(engine, "_get_latest_price", return_value=120.0):
            engine.check_stop_loss_take_profit("TEST.JK")

        # Check highest price updated
        pos = temp_storage.get_open_position("TEST.JK")
        assert pos["highest_price_since_entry"] == 120.0

        # Now price drops to 112 (below trailing stop: 120 * 0.95 = 114)
        with patch.object(engine, "_get_latest_price", return_value=112.0):
            result = engine.check_stop_loss_take_profit("TEST.JK")

        assert result is not None
        assert result["action"] == "SELL"

    def test_run_once_monitoring_mode(self, temp_storage):
        """In monitoring mode (auto_trade=false), no orders are executed."""
        os.environ.pop("AUTO_TRADE_ENABLED", None)
        engine = AutomatedExecutionEngine(storage=temp_storage)
        results = engine.run_once(["TEST.JK"])
        # No positions or orders should be created
        assert temp_storage.get_all_open_positions() == []

    def test_run_once_no_tickers(self, temp_storage):
        """Empty ticker list returns empty results."""
        with patch(
            "trading_system.utils.market_status.get_market_status",
            return_value={"is_open": True, "session": "open", "next_open": None},
        ):
            engine = AutomatedExecutionEngine(storage=temp_storage)
            results = engine.run_once([])
            assert results == []

    def test_position_size_capped_at_10pct(self, temp_storage):
        """Position size is capped at 10% of capital."""
        os.environ["TRADING_CAPITAL"] = "1000000"
        engine = AutomatedExecutionEngine(storage=temp_storage)
        price = 130.0
        qty = engine._compute_position_size("TEST.JK", price)
        max_value = qty * price
        assert max_value <= engine.capital * 0.10 + 100  # allow rounding
        os.environ.pop("TRADING_CAPITAL", None)
