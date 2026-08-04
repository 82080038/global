"""Tests for gorengan detector module."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_system.analysis.gorengan_detector import (
    GorenganReport,
    detect_gorengan,
    detect_low_liquidity,
    detect_price_spike,
    detect_volume_spike,
    detect_weak_fundamental,
)


def _make_ohlcv(n: int, base_price: float = 5000, vol_base: float = 500_000) -> pd.DataFrame:
    """Generate OHLCV DataFrame for testing."""
    dates = pd.date_range(start="2024-01-01", periods=n, freq="B")
    returns = np.random.normal(0.0, 0.01, n)
    close = base_price * np.cumprod(1 + returns)
    volume = np.random.randint(vol_base * 0.5, vol_base * 2, n).astype(float)
    return pd.DataFrame({
        "open": close,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": volume,
    }, index=dates)


class TestPriceSpike:
    def test_detects_5d_spike(self):
        np.random.seed(42)
        df = _make_ohlcv(40)
        df.iloc[-5:, df.columns.get_loc("close")] = df["close"].iloc[-5] * np.linspace(1, 1.6, 5)

        flags = detect_price_spike(df)
        assert len(flags) > 0
        assert flags[0].flag_type == "PRICE_SPIKE_5D"
        assert flags[0].severity == "critical"

    def test_no_spike_on_normal_market(self):
        np.random.seed(42)
        df = _make_ohlcv(40)
        flags = detect_price_spike(df)
        assert len(flags) == 0


class TestVolumeSpike:
    def test_detects_volume_spike(self):
        np.random.seed(42)
        df = _make_ohlcv(40)
        df.iloc[-5:, df.columns.get_loc("volume")] = df["volume"].iloc[-5] * 5

        flags = detect_volume_spike(df)
        assert len(flags) > 0
        assert flags[0].flag_type == "VOLUME_SPIKE"

    def test_no_spike_on_normal_volume(self):
        np.random.seed(42)
        df = _make_ohlcv(40)
        flags = detect_volume_spike(df)
        assert len(flags) == 0


class TestWeakFundamental:
    def test_negative_pe(self):
        flags = detect_weak_fundamental(pe_ratio=-5.0)
        assert len(flags) == 1
        assert flags[0].flag_type == "NEGATIVE_PE"
        assert flags[0].severity == "high"

    def test_extreme_pe(self):
        flags = detect_weak_fundamental(pe_ratio=150.0)
        assert len(flags) == 1
        assert flags[0].flag_type == "EXTREME_PE"

    def test_high_pe(self):
        flags = detect_weak_fundamental(pe_ratio=60.0)
        assert len(flags) == 1
        assert flags[0].severity == "medium"

    def test_normal_pe(self):
        flags = detect_weak_fundamental(pe_ratio=15.0)
        assert len(flags) == 0

    def test_low_roe(self):
        flags = detect_weak_fundamental(roe=2.0)
        assert any(f.flag_type == "LOW_ROE" for f in flags)

    def test_high_der(self):
        flags = detect_weak_fundamental(der=4.0)
        assert any(f.flag_type == "HIGH_DER" for f in flags)


class TestLowLiquidity:
    def test_detects_low_liquidity(self):
        np.random.seed(42)
        df = _make_ohlcv(40, vol_base=200_000)
        flags = detect_low_liquidity(df)
        assert len(flags) > 0
        assert flags[0].flag_type == "LOW_LIQUIDITY"

    def test_no_flag_on_liquid_stock(self):
        np.random.seed(42)
        df = _make_ohlcv(40, vol_base=20_000_000)
        flags = detect_low_liquidity(df)
        assert len(flags) == 0


class TestDetectGorengan:
    def test_detects_gorengan_pattern(self):
        np.random.seed(42)
        df = _make_ohlcv(40, vol_base=200_000)
        df.iloc[-5:, df.columns.get_loc("close")] = df["close"].iloc[-5] * np.linspace(1, 1.6, 5)
        df.iloc[-5:, df.columns.get_loc("volume")] = df["volume"].iloc[-5] * 5

        report = detect_gorengan(df, symbol="GORENG.JK", pe_ratio=-10.0)
        assert report.is_gorengan
        assert report.risk_score > 50
        assert len(report.flags) > 0

    def test_not_gorengan_on_normal_stock(self):
        np.random.seed(42)
        df = _make_ohlcv(40, vol_base=20_000_000)
        report = detect_gorengan(df, symbol="SAFE.JK", pe_ratio=15.0, roe=20.0)
        assert not report.is_gorengan
        assert report.risk_score < 30

    def test_to_dict(self):
        np.random.seed(42)
        df = _make_ohlcv(40)
        report = detect_gorengan(df, symbol="TEST.JK")
        d = report.to_dict()
        assert "symbol" in d
        assert "is_gorengan" in d
        assert "risk_score" in d
        assert "flags" in d

    def test_gorengan_with_price_spike_but_good_fundamental(self):
        np.random.seed(42)
        df = _make_ohlcv(40, vol_base=20_000_000)
        df.iloc[-5:, df.columns.get_loc("close")] = df["close"].iloc[-5] * np.linspace(1, 1.6, 5)

        report = detect_gorengan(df, symbol="MOMENTUM.JK", pe_ratio=12.0, roe=25.0)
        assert not report.is_gorengan
