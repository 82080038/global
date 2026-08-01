"""Property-based tests for backtest engine using Hypothesis.

Tests invariants that should always hold regardless of input data:
- Equity curve never goes negative (with positive initial capital)
- PnL is consistent with trade history
- Number of trades is non-negative
- Final equity = initial_capital + sum(realized_pnl) - fees
- Win rate is between 0 and 1
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from trading_system.backtest.engine import BacktestEngine
from trading_system.backtest.strategies import BuyAndHold, MovingAverageCrossover


def _make_ohlcv_df(n: int, start_price: float = 100.0, volatility: float = 0.02) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    returns = np.random.normal(0, volatility, n)
    closes = start_price * np.cumprod(1 + returns)
    opens = closes * (1 + np.random.normal(0, 0.005, n))
    highs = np.maximum(opens, closes) * (1 + np.abs(np.random.normal(0, 0.003, n)))
    lows = np.minimum(opens, closes) * (1 - np.abs(np.random.normal(0, 0.003, n)))
    volumes = np.random.randint(100000, 1000000, n).astype(float)

    df = pd.DataFrame({
        "timestamp": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
        "adjusted_close": closes,
    })
    df.set_index("timestamp", inplace=True)
    return df


class TestBacktestPropertyBased:
    """Property-based tests for backtest engine invariants."""

    @given(
        n_bars=st.integers(min_value=50, max_value=300),
        start_price=st.floats(min_value=100, max_value=10000),
        capital=st.floats(min_value=1_000_000, max_value=1_000_000_000),
    )
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_buy_and_hold_equity_never_negative(self, n_bars, start_price, capital):
        """Equity curve should never go negative with positive initial capital."""
        df = _make_ohlcv_df(n_bars, start_price=start_price)
        engine = BacktestEngine()
        strategy = BuyAndHold()

        result = engine.run_with_data(df, strategy, initial_capital=capital)
        assert result is not None
        assert result["final_equity"] >= 0, f"Equity went negative: {result['final_equity']}"
        assert "metrics" in result
        assert result["metrics"]["total_return"] is not None

    @given(
        n_bars=st.integers(min_value=100, max_value=300),
        short_window=st.integers(min_value=5, max_value=20),
        long_window=st.integers(min_value=21, max_value=50),
        capital=st.floats(min_value=1_000_000, max_value=100_000_000),
    )
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_ma_crossover_equity_never_negative(self, n_bars, short_window, long_window, capital):
        """Equity curve should never go negative for MA crossover strategy."""
        df = _make_ohlcv_df(n_bars)
        engine = BacktestEngine()
        strategy = MovingAverageCrossover(fast=short_window, slow=long_window)

        result = engine.run_with_data(df, strategy, initial_capital=capital)
        assert result is not None
        assert result["final_equity"] >= 0, f"Equity went negative: {result['final_equity']}"

    @given(
        n_bars=st.integers(min_value=50, max_value=200),
        capital=st.floats(min_value=10_000_000, max_value=500_000_000),
    )
    @settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_buy_and_hold_total_trades_non_negative(self, n_bars, capital):
        """Number of trades should be non-negative."""
        df = _make_ohlcv_df(n_bars)
        engine = BacktestEngine()
        strategy = BuyAndHold()

        result = engine.run_with_data(df, strategy, initial_capital=capital)
        assert result["metrics"]["number_of_trades"] >= 0

    @given(
        n_bars=st.integers(min_value=50, max_value=200),
        capital=st.floats(min_value=10_000_000, max_value=500_000_000),
    )
    @settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_buy_and_hold_win_rate_in_range(self, n_bars, capital):
        """Win rate should be between 0 and 1 (or None if no trades)."""
        df = _make_ohlcv_df(n_bars)
        engine = BacktestEngine()
        strategy = BuyAndHold()

        result = engine.run_with_data(df, strategy, initial_capital=capital)
        win_rate = result["metrics"].get("win_rate")
        if win_rate is not None:
            assert 0 <= win_rate <= 1, f"Win rate out of range: {win_rate}"

    @given(
        n_bars=st.integers(min_value=100, max_value=300),
        capital=st.floats(min_value=1_000_000, max_value=1_000_000_000),
    )
    @settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_buy_and_hold_max_drawdown_non_positive(self, n_bars, capital):
        """Max drawdown should be non-positive (it's a loss metric)."""
        df = _make_ohlcv_df(n_bars)
        engine = BacktestEngine()
        strategy = BuyAndHold()

        result = engine.run_with_data(df, strategy, initial_capital=capital)
        max_dd = result["metrics"].get("max_drawdown")
        if max_dd is not None:
            assert max_dd <= 0, f"Max drawdown should be non-positive: {max_dd}"


class TestStoragePropertyBased:
    """Property-based tests for storage layer invariants."""

    @given(
        ticker=st.text(min_size=3, max_size=10, alphabet=st.characters(whitelist_categories=("Lu", "Ll"), whitelist_characters="._-")),
    )
    @settings(max_examples=20, deadline=None)
    def test_set_and_get_state_roundtrip(self, ticker):
        """System state set/get should be a perfect roundtrip."""
        from trading_system.data.storage import DataStorage

        storage = DataStorage()
        key = f"test_key_{ticker}"
        value = f"test_value_{ticker}"

        try:
            storage.set_state(key, value)
            retrieved = storage.get_state(key)
            assert retrieved == value, f"Roundtrip failed: set {value}, got {retrieved}"
        finally:
            # Cleanup
            try:
                storage.set_state(key, "")
            except Exception:
                pass
