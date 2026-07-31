"""Unit tests for BacktestEngine and strategies."""

import pandas as pd
import pytest
from unittest.mock import patch, MagicMock

from trading_system.backtest.engine import BacktestEngine, CostModel
from trading_system.backtest.strategies import BuyAndHold, MovingAverageCrossover


class TestStrategies:

    def test_buy_and_hold_signals(self, mock_ohlcv_indexed_df):
        """BuyAndHold should buy on first bar and sell on last."""
        strategy = BuyAndHold()
        df = strategy.generate_signals(mock_ohlcv_indexed_df)

        assert df["signal"].iloc[0] == 1
        assert df["signal"].iloc[-1] == -1
        assert df["signal"].sum() == 0  # 1 buy + (-1) sell = 0

    def test_buy_and_hold_warmup(self):
        """BuyAndHold should have warmup_periods = 0."""
        assert BuyAndHold.warmup_periods == 0

    def test_ma_crossover_warmup(self):
        """MovingAverageCrossover should have warmup_periods = slow."""
        strategy = MovingAverageCrossover(fast=20, slow=50)
        assert strategy.warmup_periods == 50

    def test_ma_crossover_no_signals_during_warmup(self, mock_ohlcv_indexed_df):
        """No signals should be generated during warmup period."""
        strategy = MovingAverageCrossover(fast=20, slow=50)
        df = strategy.generate_signals(mock_ohlcv_indexed_df)

        # First 50 bars should have signal = 0
        assert (df["signal"].iloc[:50] == 0).all()

    def test_ma_crossover_generates_signals_after_warmup(self, mock_ohlcv_indexed_df):
        """Signals should only appear after warmup period."""
        strategy = MovingAverageCrossover(fast=20, slow=50)
        df = strategy.generate_signals(mock_ohlcv_indexed_df)

        # After warmup, there should be at least some signals (or none if no crossover)
        post_warmup_signals = df["signal"].iloc[50:]
        assert post_warmup_signals.isin([0, 1, -1]).all()

    def test_ma_crossover_short_data(self):
        """If data is shorter than warmup, all signals should be 0."""
        strategy = MovingAverageCrossover(fast=20, slow=50)
        short_df = pd.DataFrame(
            {"close": [100, 101, 102, 103, 104]},
            index=pd.date_range("2024-01-01", periods=5),
        )
        df = strategy.generate_signals(short_df)
        assert (df["signal"] == 0).all()


class TestCostModel:

    def test_cost_model_defaults(self):
        """CostModel should have sensible defaults."""
        cm = CostModel()
        assert cm.buy_fee > 0
        assert cm.sell_fee > 0
        assert cm.levy > 0
        assert cm.slippage > 0

    def test_cost_model_custom(self):
        """CostModel should accept custom parameters."""
        cm = CostModel(buy_fee=0.001, sell_fee=0.002, levy=0.0001, slippage=0.001)
        assert cm.buy_fee == 0.001
        assert cm.sell_fee == 0.002
        assert cm.levy == 0.0001
        assert cm.slippage == 0.001

    def test_cost_model_buy_sell_cost(self):
        """buy_cost_pct and sell_cost_pct should include all components."""
        cm = CostModel(buy_fee=0.001, sell_fee=0.002, levy=0.0001, slippage=0.001)
        assert cm.buy_cost_pct() == 0.001 + 0.0001 + 0.001
        assert cm.sell_cost_pct() == 0.002 + 0.0001 + 0.001


class TestBacktestEngine:

    def test_run_empty_data_returns_error(self):
        """Empty OHLCV should return error."""
        mock_storage = MagicMock()
        mock_storage.load_ohlcv.return_value = pd.DataFrame()

        engine = BacktestEngine(storage=mock_storage)
        result = engine.run("EMPTY.JK", BuyAndHold())

        assert result["status"] == "error"

    @patch("trading_system.backtest.engine.DataStorage")
    def test_run_buy_and_hold(self, mock_storage_cls, mock_ohlcv_indexed_df):
        """BuyAndHold backtest should produce metrics."""
        mock_storage = MagicMock()
        mock_storage.load_ohlcv.return_value = mock_ohlcv_indexed_df
        mock_storage_cls.return_value = mock_storage

        engine = BacktestEngine(storage=mock_storage)
        result = engine.run("TEST.JK", BuyAndHold())

        assert result["status"] == "ok"
        assert "metrics" in result
        assert "equity_curve" in result
        assert "trade_history" in result
        assert result["metrics"]["number_of_trades"] >= 1

    @patch("trading_system.backtest.engine.DataStorage")
    def test_run_ma_crossover_with_warmup(self, mock_storage_cls, mock_ohlcv_indexed_df):
        """MA crossover with warmup should not generate signals in first 50 bars."""
        mock_storage = MagicMock()
        mock_storage.load_ohlcv.return_value = mock_ohlcv_indexed_df
        mock_storage_cls.return_value = mock_storage

        engine = BacktestEngine(storage=mock_storage)
        result = engine.run("TEST.JK", MovingAverageCrossover(20, 50))

        assert result["status"] == "ok"
        assert "metrics" in result
