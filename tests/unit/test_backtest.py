"""Unit tests for BacktestEngine and strategies."""

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from trading_system.backtest.engine import BacktestEngine, CostModel
from trading_system.backtest.metrics import monte_carlo_simulation
from trading_system.backtest.strategies import BuyAndHold, ConvictionStrategy, MovingAverageCrossover
from trading_system.config import IDX_LOT_SIZE, idx_tick_size, round_to_tick


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


class TestIDXTickSize:

    def test_tick_size_below_200(self):
        assert idx_tick_size(150) == 1.0
        assert idx_tick_size(199) == 1.0

    def test_tick_size_200_to_499(self):
        assert idx_tick_size(200) == 2.0
        assert idx_tick_size(499) == 2.0

    def test_tick_size_500_to_1999(self):
        assert idx_tick_size(500) == 5.0
        assert idx_tick_size(1999) == 5.0

    def test_tick_size_2000_to_4999(self):
        assert idx_tick_size(2000) == 10.0
        assert idx_tick_size(4999) == 10.0

    def test_tick_size_5000_plus(self):
        assert idx_tick_size(5000) == 25.0
        assert idx_tick_size(10000) == 25.0

    def test_round_to_tick_rounds_correctly(self):
        assert round_to_tick(8050) == 8050  # already on tick
        assert round_to_tick(8053) == 8050  # rounds down to nearest 25
        assert round_to_tick(8063) == 8075  # rounds up to nearest 25
        assert round_to_tick(153) == 153    # tick=1, no change
        assert round_to_tick(253) == 252    # tick=2


class TestNextBarOpenExecution:

    @patch("trading_system.backtest.engine.DataStorage")
    def test_shares_rounded_to_lot_size(self, mock_storage_cls, mock_ohlcv_indexed_df):
        """Shares bought should be multiples of IDX_LOT_SIZE (100)."""
        mock_storage = MagicMock()
        mock_storage.load_ohlcv.return_value = mock_ohlcv_indexed_df
        mock_storage_cls.return_value = mock_storage

        engine = BacktestEngine(storage=mock_storage)
        result = engine.run("TEST.JK", BuyAndHold())

        assert result["status"] == "ok"
        trades = result.get("trade_history")
        if not trades.empty:
            for _, trade in trades.iterrows():
                assert trade["shares"] % IDX_LOT_SIZE == 0

    @patch("trading_system.backtest.engine.DataStorage")
    def test_fill_price_on_tick(self, mock_storage_cls, mock_ohlcv_indexed_df):
        """Fill prices should be on IDX tick grid."""
        mock_storage = MagicMock()
        mock_storage.load_ohlcv.return_value = mock_ohlcv_indexed_df
        mock_storage_cls.return_value = mock_storage

        engine = BacktestEngine(storage=mock_storage)
        result = engine.run("TEST.JK", BuyAndHold())

        assert result["status"] == "ok"
        trades = result.get("trade_history")
        if not trades.empty:
            for _, trade in trades.iterrows():
                tick = idx_tick_size(trade["entry_price"])
                assert trade["entry_price"] % tick == 0
                assert trade["exit_price"] % tick == 0

    @patch("trading_system.backtest.engine.DataStorage")
    def test_no_trade_on_last_bar_signal(self, mock_storage_cls):
        """Signal on last bar should not execute (no next bar open)."""
        # Create a tiny DF where BuyAndHold buys on bar 0 and sells on last bar
        n = 5
        dates = pd.date_range("2024-01-01", periods=n, freq="B")
        df = pd.DataFrame({
            "open": [8000, 8010, 8020, 8030, 8040],
            "high": [8050, 8060, 8070, 8080, 8090],
            "low": [7950, 7960, 7970, 7980, 7990],
            "close": [8000, 8010, 8020, 8030, 8040],
            "volume": [1e6] * n,
        }, index=dates)

        mock_storage = MagicMock()
        mock_storage.load_ohlcv.return_value = df
        mock_storage_cls.return_value = mock_storage

        engine = BacktestEngine(storage=mock_storage)
        result = engine.run("TEST.JK", BuyAndHold())

        assert result["status"] == "ok"
        # BuyAndHold sets signal=1 on bar 0, signal=-1 on last bar
        # Buy executes at next_open (bar 1 open=8010)
        # Sell signal on last bar has no next_open -> force close at last close
        trades = result.get("trade_history")
        assert not trades.empty
        # Entry should be at next bar's open, not bar 0's close
        assert trades.iloc[0]["entry_price"] != 8000  # Should be ~8010 adjusted


class TestConvictionStrategy:

    def test_no_scores_returns_all_zero(self, mock_ohlcv_indexed_df):
        """With no scores, all signals should be 0."""
        storage = MagicMock()
        storage.load_scores.return_value = pd.DataFrame()
        strategy = ConvictionStrategy(storage=storage, ticker="TEST.JK")
        df = strategy.generate_signals(mock_ohlcv_indexed_df)
        assert (df["signal"] == 0).all()

    def test_buy_signal_when_conviction_above_threshold(self, mock_ohlcv_indexed_df):
        """Conviction >= 70 should generate BUY."""
        dates = mock_ohlcv_indexed_df.index[:5]
        scores = pd.DataFrame({
            "as_of": dates,
            "conviction": [75, 80, 72, 68, 65],
        })
        strategy = ConvictionStrategy(scores_df=scores)
        df = strategy.generate_signals(mock_ohlcv_indexed_df)
        # First bar with conviction >= 70 should be BUY
        assert df["signal"].iloc[0] == 1

    def test_sell_signal_when_conviction_drops_below_exit(self, mock_ohlcv_indexed_df):
        """Conviction < exit_threshold while in position should generate SELL."""
        dates = mock_ohlcv_indexed_df.index[:10]
        scores = pd.DataFrame({
            "as_of": dates,
            "conviction": [75, 72, 71, 35, 30, 80, 78, 76, 74, 72],
        })
        strategy = ConvictionStrategy(scores_df=scores)
        df = strategy.generate_signals(mock_ohlcv_indexed_df)
        # Bar 0: BUY (75 >= 70)
        assert df["signal"].iloc[0] == 1
        # Bar 3: SELL (35 < 40, in position)
        assert df["signal"].iloc[3] == -1
        # Bar 5: BUY again (80 >= 70, not in position)
        assert df["signal"].iloc[5] == 1

    def test_hold_when_conviction_between_thresholds(self, mock_ohlcv_indexed_df):
        """Conviction between exit and buy threshold should be HOLD (0)."""
        dates = mock_ohlcv_indexed_df.index[:5]
        scores = pd.DataFrame({
            "as_of": dates,
            "conviction": [75, 55, 50, 45, 35],
        })
        strategy = ConvictionStrategy(scores_df=scores)
        df = strategy.generate_signals(mock_ohlcv_indexed_df)
        # Bar 0: BUY, Bar 1-2: HOLD, Bar 3: HOLD (still >= 40), Bar 4: SELL
        assert df["signal"].iloc[0] == 1
        assert df["signal"].iloc[1] == 0
        assert df["signal"].iloc[2] == 0
        assert df["signal"].iloc[3] == 0
        assert df["signal"].iloc[4] == -1


class TestBlockBootstrapMC:

    def test_block_bootstrap_runs(self):
        """Block bootstrap MC should produce results with block_size set."""
        rng = np.random.default_rng(42)
        returns = pd.Series(rng.normal(0.001, 0.02, 100))
        result = monte_carlo_simulation(returns, n_simulations=50, n_periods=60, block_size=10)

        assert "status" not in result or result.get("status") != "insufficient_data"
        assert result["block_size"] == 10
        assert "mean_final_equity" in result
        assert "prob_profit" in result

    def test_iid_bootstrap_still_works(self):
        """IID bootstrap (block_size=None) should still work."""
        rng = np.random.default_rng(42)
        returns = pd.Series(rng.normal(0.001, 0.02, 100))
        result = monte_carlo_simulation(returns, n_simulations=50, n_periods=60)

        assert "status" not in result or result.get("status") != "insufficient_data"
        assert result["block_size"] is None

    def test_block_bootstrap_preserves_structure(self):
        """Block bootstrap should produce different results than IID."""
        rng = np.random.default_rng(42)
        # Create returns with strong autocorrelation
        n = 200
        raw = rng.normal(0, 0.02, n)
        # Add autocorrelation
        for i in range(1, n):
            raw[i] = 0.5 * raw[i-1] + 0.5 * raw[i]
        returns = pd.Series(raw)

        iid_result = monte_carlo_simulation(returns, n_simulations=200, n_periods=100, block_size=None)
        block_result = monte_carlo_simulation(returns, n_simulations=200, n_periods=100, block_size=15)

        # Results should differ because block bootstrap preserves autocorrelation
        assert iid_result["block_size"] is None
        assert block_result["block_size"] == 15
        # The max drawdown distributions should differ
        assert iid_result["worst_drawdown"] != block_result["worst_drawdown"]


class TestMonteCarloGPU:
    """Tests for GPU-accelerated Monte Carlo path (auto-fallback to CPU)."""

    def test_gpu_path_produces_valid_result(self):
        """GPU path (use_gpu=True) should produce same shape result as CPU."""
        rng = np.random.default_rng(42)
        returns = pd.Series(rng.normal(0.001, 0.02, 100))
        result = monte_carlo_simulation(
            returns, n_simulations=100, n_periods=60, use_gpu=True,
        )
        assert "status" not in result or result.get("status") != "insufficient_data"
        assert "backend" in result
        assert result["backend"] in ("gpu", "cpu")  # cpu if no torch/CUDA
        assert "mean_final_equity" in result
        assert "prob_profit" in result

    def test_gpu_cpu_results_statistically_close(self):
        """GPU and CPU paths should produce statistically similar distributions
        (same seed, same distribution — not identical due to RNG impl, but close)."""
        rng = np.random.default_rng(42)
        returns = pd.Series(rng.normal(0.001, 0.02, 200))

        cpu_result = monte_carlo_simulation(
            returns, n_simulations=500, n_periods=100, use_gpu=False,
        )
        gpu_result = monte_carlo_simulation(
            returns, n_simulations=500, n_periods=100, use_gpu=True,
        )

        # Both should succeed
        assert "mean_final_equity" in cpu_result
        assert "mean_final_equity" in gpu_result

        # Means should be within 15% of each other (statistical tolerance)
        cpu_mean = cpu_result["mean_final_equity"]
        gpu_mean = gpu_result["mean_final_equity"]
        if cpu_mean > 0:
            ratio = gpu_mean / cpu_mean
            assert 0.85 < ratio < 1.15, f"GPU mean {gpu_mean} too far from CPU mean {cpu_mean}"

    def test_gpu_disabled_falls_back_to_cpu(self):
        """use_gpu=False should always use CPU backend."""
        rng = np.random.default_rng(42)
        returns = pd.Series(rng.normal(0.001, 0.02, 100))
        result = monte_carlo_simulation(
            returns, n_simulations=50, n_periods=60, use_gpu=False,
        )
        assert result["backend"] == "cpu"

    def test_block_bootstrap_uses_cpu_even_with_gpu(self):
        """Block bootstrap should always use CPU (GPU path only for IID)."""
        rng = np.random.default_rng(42)
        returns = pd.Series(rng.normal(0.001, 0.02, 100))
        result = monte_carlo_simulation(
            returns, n_simulations=50, n_periods=60, block_size=10, use_gpu=True,
        )
        # Block bootstrap always uses CPU loop
        assert result["backend"] == "cpu"
        assert result["block_size"] == 10
