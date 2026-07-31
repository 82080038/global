"""Unit tests for consolidated costs module (P2-4)."""

import numpy as np
import pandas as pd

from trading_system.risk.costs import (
    CostModel,
    compute_atr,
    get_default_cost_model,
    get_latest_atr,
)


def _make_ohlcv(n=50, start_price=1000):
    rng = np.random.RandomState(42)
    dates = pd.bdate_range("2024-01-01", periods=n)
    close = start_price * np.cumprod(1 + rng.normal(0.001, 0.015, n))
    high = close * (1 + np.abs(rng.normal(0, 0.01, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.01, n)))
    return pd.DataFrame({
        "open": close, "high": high, "low": low, "close": close,
        "volume": np.random.randint(1e6, 5e7, n).astype(float),
    }, index=dates)


class TestComputeATR:
    def test_atr_series_length(self):
        df = _make_ohlcv(50)
        atr = compute_atr(df, 14)
        assert len(atr) == 50
        assert atr.isna().sum() == 13  # first 13 are NaN

    def test_atr_positive(self):
        df = _make_ohlcv(50)
        atr = compute_atr(df, 14)
        valid = atr.dropna()
        assert all(v > 0 for v in valid)

    def test_atr_short_data(self):
        df = _make_ohlcv(5)
        atr = compute_atr(df, 14)
        assert atr.isna().all()


class TestGetLatestATR:
    def test_latest_atr(self):
        df = _make_ohlcv(50)
        atr = get_latest_atr(df, 14)
        assert atr > 0

    def test_latest_atr_insufficient(self):
        df = _make_ohlcv(5)
        assert get_latest_atr(df, 14) == 0.0

    def test_latest_atr_empty(self):
        assert get_latest_atr(pd.DataFrame(), 14) == 0.0

    def test_latest_atr_none(self):
        assert get_latest_atr(None, 14) == 0.0


class TestCostModel:
    def test_buy_cost_pct(self):
        cm = CostModel()
        assert cm.buy_cost_pct() == cm.buy_fee + cm.levy + cm.slippage

    def test_sell_cost_pct(self):
        cm = CostModel()
        assert cm.sell_cost_pct() == cm.sell_fee + cm.levy + cm.slippage

    def test_compute_fees_buy(self):
        cm = CostModel()
        fees = cm.compute_fees(10_000_000, "buy")
        assert fees["brokerage"] > 0
        assert fees["levy"] > 0
        assert fees["tax"] == 0  # no tax on buy
        assert fees["total"] == fees["brokerage"] + fees["levy"] + fees["tax"]

    def test_compute_fees_sell(self):
        cm = CostModel()
        fees = cm.compute_fees(10_000_000, "sell")
        assert fees["brokerage"] > 0
        assert fees["tax"] > 0  # PPh on sell
        assert fees["total"] == fees["brokerage"] + fees["levy"] + fees["tax"]

    def test_estimate_slippage_small_order(self):
        cm = CostModel()
        slip = cm.estimate_slippage(500_000, 1_000_000_000)  # ratio = 0.0005 < 0.001
        assert slip == cm.slippage

    def test_estimate_slippage_medium_order(self):
        cm = CostModel()
        slip = cm.estimate_slippage(5_000_000, 1_000_000_000)  # ratio = 0.005
        assert slip == cm.slippage * 2

    def test_estimate_slippage_large_order(self):
        cm = CostModel()
        slip = cm.estimate_slippage(50_000_000, 1_000_000_000)  # ratio = 0.05
        assert slip == cm.slippage * 4

    def test_estimate_slippage_no_volume(self):
        cm = CostModel()
        slip = cm.estimate_slippage(10_000_000, 0)
        assert slip == cm.slippage

    def test_simulate_fill_buy(self):
        cm = CostModel()
        result = cm.simulate_fill("buy", 100, 5000, 1_000_000_000)
        assert result["action"] == "BUY"
        assert result["fill_price"] > 5000  # slippage increases buy price
        assert result["fees"]["total"] > 0

    def test_simulate_fill_sell(self):
        cm = CostModel()
        result = cm.simulate_fill("sell", 100, 5000, 1_000_000_000)
        assert result["action"] == "SELL"
        assert result["fill_price"] < 5000  # slippage decreases sell price

    def test_check_feasibility_sufficient(self):
        cm = CostModel()
        result = cm.check_feasibility(100, 5000, 10_000_000, 1_000_000_000)
        assert result["feasible"] is True

    def test_check_feasibility_insufficient(self):
        cm = CostModel()
        result = cm.check_feasibility(100, 5000, 100, 1_000_000_000)
        assert result["feasible"] is False


class TestDefaultCostModel:
    def test_singleton(self):
        cm1 = get_default_cost_model()
        cm2 = get_default_cost_model()
        assert cm1 is cm2

    def test_default_rates(self):
        cm = get_default_cost_model()
        assert cm.buy_fee == 0.0015
        assert cm.sell_fee == 0.0025
        assert cm.levy == 0.0000043
        assert cm.slippage == 0.0005
