"""Tests for shared execution interface (TradingInterface)."""

import pytest
from unittest.mock import MagicMock, patch

from trading_system.config import TRADING_CAPITAL
from trading_system.execution import get_execution_engine
from trading_system.execution.interface import TradingInterface
from trading_system.execution.paper_execution import PaperExecutionEngine
from trading_system.execution.real_execution import RealExecutionEngine


class TestTradingInterface:
    """Test the abstract base class and factory function."""

    def test_get_execution_engine_paper_mode(self):
        """Test factory function returns PaperExecutionEngine for paper mode."""
        storage = MagicMock()
        executor = get_execution_engine(storage, TRADING_CAPITAL, mode="paper")
        assert isinstance(executor, PaperExecutionEngine)
        assert isinstance(executor, TradingInterface)

    def test_get_execution_engine_real_mode(self):
        """Test factory function returns RealExecutionEngine for real mode."""
        storage = MagicMock()
        executor = get_execution_engine(storage, TRADING_CAPITAL, mode="real")
        assert isinstance(executor, RealExecutionEngine)
        assert isinstance(executor, TradingInterface)

    def test_get_execution_engine_invalid_mode(self):
        """Test factory function raises ValueError for invalid mode."""
        storage = MagicMock()
        with pytest.raises(ValueError, match="Invalid TRADING_MODE"):
            get_execution_engine(storage, TRADING_CAPITAL, mode="invalid")

    def test_get_execution_engine_default_mode(self):
        """Test factory function uses TRADING_MODE from config when mode not specified."""
        storage = MagicMock()
        # Test with default (should be paper)
        executor = get_execution_engine(storage)
        assert isinstance(executor, PaperExecutionEngine)


class TestPaperExecutionEngine:
    """Test PaperExecutionEngine implementation."""

    def test_execute_order_buy(self):
        """Test paper execution of BUY order."""
        storage = MagicMock()
        
        # Create a proper mock DataFrame
        mock_df = MagicMock()
        mock_df.empty = False
        mock_df.__getitem__ = lambda self, key: MagicMock(
            iloc=MagicMock(__getitem__=lambda self, idx: 10000 if key == "close" else None)
        ) if key == "close" else MagicMock(
            tail=MagicMock(return_value=MagicMock(mean=MagicMock(return_value=1000000)))
        )
        storage.load_ohlcv.return_value = mock_df

        engine = PaperExecutionEngine(storage, cash=1_000_000_000)
        order = {
            "ticker": "BBCA.JK",
            "action": "buy",
            "shares": 100,
            "target_price": 10000,
        }

        result = engine.execute_order(order)
        assert result["status"] == "ok"
        assert "order_id" in result

    def test_execute_order_sell(self):
        """Test paper execution of SELL order."""
        storage = MagicMock()
        
        # Create a proper mock DataFrame
        mock_df = MagicMock()
        mock_df.empty = False
        mock_df.__getitem__ = lambda self, key: MagicMock(
            iloc=MagicMock(__getitem__=lambda self, idx: 10000 if key == "close" else None)
        ) if key == "close" else MagicMock(
            tail=MagicMock(return_value=MagicMock(mean=MagicMock(return_value=1000000)))
        )
        storage.load_ohlcv.return_value = mock_df

        engine = PaperExecutionEngine(storage, cash=1_000_000_000)
        
        # First buy to create position
        buy_order = {
            "ticker": "BBCA.JK",
            "action": "buy",
            "shares": 100,
            "target_price": 10000,
        }
        engine.execute_order(buy_order)

        # Then sell
        sell_order = {
            "ticker": "BBCA.JK",
            "action": "sell",
            "shares": 50,
            "target_price": 10500,
        }

        result = engine.execute_order(sell_order)
        assert result["status"] == "ok"
        assert "order_id" in result

    def test_get_position(self):
        """Test getting paper position."""
        storage = MagicMock()
        
        # Create a proper mock DataFrame
        mock_df = MagicMock()
        mock_df.empty = False
        mock_df.__getitem__ = lambda self, key: MagicMock(
            iloc=MagicMock(__getitem__=lambda self, idx: 10000 if key == "close" else None)
        ) if key == "close" else MagicMock(
            tail=MagicMock(return_value=MagicMock(mean=MagicMock(return_value=1000000)))
        )
        storage.load_ohlcv.return_value = mock_df

        engine = PaperExecutionEngine(storage, cash=1_000_000_000)
        
        # Create position
        order = {
            "ticker": "BBCA.JK",
            "action": "buy",
            "shares": 100,
            "target_price": 10000,
        }
        engine.execute_order(order)

        position = engine.get_position("BBCA.JK")
        assert position is not None
        assert position["ticker"] == "BBCA.JK"
        assert position["shares"] == 100
        assert "unrealized_pnl" in position

    def test_get_portfolio_summary(self):
        """Test getting paper portfolio summary."""
        storage = MagicMock()
        
        # Create a proper mock DataFrame
        mock_df = MagicMock()
        mock_df.empty = False
        mock_df.__getitem__ = lambda self, key: MagicMock(
            iloc=MagicMock(__getitem__=lambda self, idx: 10000 if key == "close" else None)
        ) if key == "close" else MagicMock(
            tail=MagicMock(return_value=MagicMock(mean=MagicMock(return_value=1000000)))
        )
        storage.load_ohlcv.return_value = mock_df

        engine = PaperExecutionEngine(storage, cash=1_000_000_000)
        
        # Create position
        order = {
            "ticker": "BBCA.JK",
            "action": "buy",
            "shares": 100,
            "target_price": 10000,
        }
        engine.execute_order(order)

        summary = engine.get_portfolio_summary()
        assert summary["cash_balance"] < 1_000_000_000  # Cash reduced after buy
        assert summary["positions_count"] == 1
        assert "total_value" in summary
        assert "return_pct" in summary

    def test_reset(self):
        """Test resetting paper trading state."""
        storage = MagicMock()
        engine = PaperExecutionEngine(storage, cash=1_000_000_000)
        
        # Create position
        order = {
            "ticker": "BBCA.JK",
            "action": "buy",
            "shares": 100,
            "target_price": 10000,
        }
        engine.execute_order(order)

        # Reset
        result = engine.reset()
        assert result["status"] == "ok"
        assert result["initial_capital"] == 1_000_000_000

        # Verify state reset
        assert engine.get_position("BBCA.JK") is None
        summary = engine.get_portfolio_summary()
        assert summary["cash_balance"] == 1_000_000_000


class TestRealExecutionEngine:
    """Test RealExecutionEngine implementation."""

    @patch.dict("os.environ", {"AUTO_TRADE_ENABLED": "false"})
    def test_execute_order_disabled(self):
        """Test real execution when AUTO_TRADE_ENABLED is false."""
        storage = MagicMock()
        engine = RealExecutionEngine(storage, capital=1_000_000_000)
        
        order = {
            "ticker": "BBCA.JK",
            "action": "buy",
            "shares": 100,
            "target_price": 10000,
        }

        result = engine.execute_order(order)
        assert result["status"] == "skipped"
        assert "monitoring mode" in result["message"].lower()

    @patch.dict("os.environ", {"AUTO_TRADE_ENABLED": "true"})
    def test_execute_order_enabled(self):
        """Test real execution when AUTO_TRADE_ENABLED is true."""
        storage = MagicMock()
        
        # Create a proper mock DataFrame
        mock_df = MagicMock()
        mock_df.empty = False
        mock_df.__getitem__ = lambda self, key: MagicMock(
            iloc=MagicMock(__getitem__=lambda self, idx: 10000 if key == "close" else None)
        ) if key == "close" else MagicMock(
            tail=MagicMock(return_value=MagicMock(mean=MagicMock(return_value=1000000)))
        )
        storage.load_ohlcv.return_value = mock_df
        storage.get_cash_balance.return_value = 1_000_000_000
        storage.save_order.return_value = "ORDER_123"
        storage.save_position.return_value = "POS_123"

        engine = RealExecutionEngine(storage, capital=1_000_000_000)
        
        order = {
            "ticker": "BBCA.JK",
            "action": "buy",
            "shares": 100,
            "target_price": 10000,
        }

        result = engine.execute_order(order)
        assert result["status"] == "ok"
        assert "order_id" in result

    def test_get_position(self):
        """Test getting real position."""
        storage = MagicMock()
        storage.get_open_position.return_value = {
            "id": 1,
            "ticker": "BBCA.JK",
            "quantity": 100,
            "avg_entry_price": 10000,
            "created_at": "2024-01-01T00:00:00Z",
        }
        storage.load_ohlcv.return_value = MagicMock(
            empty=False,
            __getitem__=lambda self, key: MagicMock(iloc=[10500]) if key == "close" else MagicMock()
        )

        engine = RealExecutionEngine(storage)
        position = engine.get_position("BBCA.JK")
        
        assert position is not None
        assert position["ticker"] == "BBCA.JK"
        assert position["shares"] == 100
        assert position["unrealized_pnl"] == 50000  # (10500 - 10000) * 100

    def test_cancel_order(self):
        """Test order cancellation (not supported)."""
        storage = MagicMock()
        engine = RealExecutionEngine(storage)
        
        result = engine.cancel_order("ORDER_123")
        assert result["status"] == "error"
        assert "not supported" in result["message"].lower()
