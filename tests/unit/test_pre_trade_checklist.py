"""Tests for pre-trade checklist module."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_system.risk.pre_trade_checklist import (
    ChecklistResult,
    PreTradeReport,
    check_behavioral_risk,
    check_free_float,
    check_fundamental_score,
    check_liquidity,
    check_position_size,
    check_risk_reward,
    check_sector_concentration,
    run_pre_trade_checklist,
)


def _make_ohlcv(n: int, vol_base: float = 5_000_000) -> pd.DataFrame:
    """Generate OHLCV DataFrame for testing."""
    dates = pd.date_range(start="2024-01-01", periods=n, freq="B")
    close = np.linspace(8000, 8500, n) + np.random.normal(0, 50, n)
    volume = np.random.randint(vol_base * 0.5, vol_base * 2, n).astype(float)
    return pd.DataFrame({
        "open": close,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": volume,
    }, index=dates)


class TestFundamentalScoreCheck:
    def test_pass_on_good_score(self):
        result = check_fundamental_score(75.0)
        assert result.status == "PASS"

    def test_fail_on_low_score(self):
        result = check_fundamental_score(30.0)
        assert result.status == "FAIL"

    def test_warn_on_missing_score(self):
        result = check_fundamental_score(None)
        assert result.status == "WARN"


class TestLiquidityCheck:
    def test_pass_on_liquid_stock(self):
        np.random.seed(42)
        df = _make_ohlcv(40, vol_base=10_000_000)
        result = check_liquidity(df)
        assert result.status == "PASS"

    def test_fail_on_illiquid_stock(self):
        np.random.seed(42)
        df = _make_ohlcv(40, vol_base=100_000)
        result = check_liquidity(df)
        assert result.status == "FAIL"

    def test_warn_on_insufficient_data(self):
        df = _make_ohlcv(10)
        result = check_liquidity(df)
        assert result.status == "WARN"


class TestPositionSizeCheck:
    def test_pass_on_normal_risk(self):
        result = check_position_size(
            capital=100_000_000, entry=8000, stop_loss=7600, risk_pct=0.01
        )
        assert result.status == "PASS"

    def test_fail_on_excessive_risk(self):
        result = check_position_size(
            capital=100_000_000, entry=8000, stop_loss=7600, risk_pct=0.05
        )
        assert result.status == "FAIL"

    def test_fail_on_zero_risk_per_share(self):
        result = check_position_size(
            capital=100_000_000, entry=8000, stop_loss=8000, risk_pct=0.01
        )
        assert result.status == "FAIL"


class TestSectorConcentration:
    def test_pass_on_low_exposure(self):
        result = check_sector_concentration("banking", {"banking": 0.15})
        assert result.status == "PASS"

    def test_fail_on_over_concentrated(self):
        result = check_sector_concentration("banking", {"banking": 0.40})
        assert result.status == "FAIL"

    def test_warn_on_near_limit(self):
        result = check_sector_concentration("banking", {"banking": 0.28})
        assert result.status == "WARN"


class TestFreeFloatCheck:
    def test_pass_on_adequate_free_float(self):
        result = check_free_float(25.0)
        assert result.status == "PASS"

    def test_fail_on_low_free_float(self):
        result = check_free_float(8.0)
        assert result.status == "FAIL"

    def test_warn_on_missing_data(self):
        result = check_free_float(None)
        assert result.status == "WARN"


class TestRiskRewardCheck:
    def test_pass_on_good_rr(self):
        result = check_risk_reward(entry=8000, stop_loss=7600, target=9000)
        assert result.status == "PASS"
        assert result.value == 2.5

    def test_fail_on_poor_rr(self):
        result = check_risk_reward(entry=8000, stop_loss=7600, target=8200)
        assert result.status == "FAIL"

    def test_fail_on_zero_risk(self):
        result = check_risk_reward(entry=8000, stop_loss=8000, target=9000)
        assert result.status == "FAIL"


class TestBehavioralRiskCheck:
    def test_pass_on_calm_market(self):
        np.random.seed(42)
        df = _make_ohlcv(100)
        result = check_behavioral_risk(df)
        assert result.status in ("PASS", "WARN")

    def test_warn_on_high_risk(self):
        np.random.seed(42)
        df = _make_ohlcv(60)
        df.iloc[-10:, df.columns.get_loc("close")] = df["close"].iloc[-10] * np.linspace(1, 1.6, 10)
        df.iloc[-10:, df.columns.get_loc("volume")] = df["volume"].iloc[-10] * 5
        result = check_behavioral_risk(df)
        assert result.status == "WARN"


class TestRunPreTradeChecklist:
    def test_full_checklist_pass(self):
        np.random.seed(42)
        df = _make_ohlcv(40, vol_base=10_000_000)
        report = run_pre_trade_checklist(
            ticker="BBCA.JK",
            df=df,
            entry=8000,
            stop_loss=7600,
            target=9000,
            capital=100_000_000,
            risk_pct=0.01,
            fundamental_score=75.0,
            free_float_pct=30.0,
            sector="banking",
            portfolio_sector_exposure={"banking": 0.15},
            pe_ratio=15.0,
            roe=20.0,
        )
        assert report.can_proceed
        assert report.fail_count == 0

    def test_full_checklist_fail_on_gorengan(self):
        np.random.seed(42)
        df = _make_ohlcv(40, vol_base=200_000)
        df.iloc[-5:, df.columns.get_loc("close")] = df["close"].iloc[-5] * np.linspace(1, 1.6, 5)
        df.iloc[-5:, df.columns.get_loc("volume")] = df["volume"].iloc[-5] * 5
        report = run_pre_trade_checklist(
            ticker="GORENG.JK",
            df=df,
            entry=5000,
            stop_loss=4750,
            target=5500,
            capital=100_000_000,
            risk_pct=0.01,
            fundamental_score=20.0,
            free_float_pct=5.0,
            pe_ratio=-10.0,
        )
        assert not report.can_proceed
        assert report.fail_count > 0

    def test_to_dict(self):
        np.random.seed(42)
        df = _make_ohlcv(40, vol_base=10_000_000)
        report = run_pre_trade_checklist(
            ticker="TEST.JK",
            df=df,
            entry=8000,
            stop_loss=7600,
            target=9000,
            capital=100_000_000,
        )
        d = report.to_dict()
        assert "ticker" in d
        assert "can_proceed" in d
        assert "checks" in d
        assert "summary" in d
