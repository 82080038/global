"""Tests for behavioral risk score module."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_system.analysis.behavioral_risk import (
    BehavioralBias,
    BehavioralRiskReport,
    assess_behavioral_risk,
    detect_anchoring,
    detect_disposition_effect,
    detect_fomo_herding,
    detect_loss_aversion,
    detect_overconfidence,
    detect_recency_bias,
)


def _make_ohlcv(n: int, base_price: float = 8000, trend: float = 0.0, vol_base: float = 5_000_000) -> pd.DataFrame:
    """Generate OHLCV DataFrame for testing."""
    dates = pd.date_range(start="2024-01-01", periods=n, freq="B")
    returns = np.random.normal(trend, 0.015, n)
    close = base_price * np.cumprod(1 + returns)
    volume = np.random.randint(vol_base * 0.5, vol_base * 2, n).astype(float)
    return pd.DataFrame({
        "open": close,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": volume,
    }, index=dates)


class TestFomoHerding:
    def test_detects_fomo_on_sharp_rise_with_volume_spike(self):
        np.random.seed(42)
        df = _make_ohlcv(60, trend=0.0)
        df.iloc[-10:, df.columns.get_loc("close")] = df["close"].iloc[-10] * np.linspace(1, 1.3, 10)
        df.iloc[-10:, df.columns.get_loc("volume")] = df["volume"].iloc[-10] * 3

        biases = detect_fomo_herding(df)
        assert len(biases) > 0
        assert biases[0].bias_type == "FOMO_HERDING"
        assert biases[0].severity in ("medium", "high")

    def test_no_fomo_on_normal_market(self):
        np.random.seed(42)
        df = _make_ohlcv(60, trend=0.001)
        biases = detect_fomo_herding(df)
        assert len(biases) == 0

    def test_insufficient_data(self):
        df = _make_ohlcv(5)
        biases = detect_fomo_herding(df)
        assert len(biases) == 0


class TestLossAversion:
    def test_detects_loss_aversion_on_downtrend(self):
        np.random.seed(42)
        df = _make_ohlcv(100, trend=-0.002)
        df.iloc[-30:, df.columns.get_loc("volume")] = df["volume"].iloc[-30] * 0.5

        biases = detect_loss_aversion(df)
        assert len(biases) > 0
        assert biases[0].bias_type == "LOSS_AVERSION"

    def test_no_loss_aversion_on_uptrend(self):
        np.random.seed(42)
        df = _make_ohlcv(100, trend=0.002)
        biases = detect_loss_aversion(df)
        assert len(biases) == 0


class TestOverconfidence:
    def test_detects_high_turnover(self):
        np.random.seed(42)
        df = _make_ohlcv(80)
        df.iloc[-20:, df.columns.get_loc("volume")] = df["volume"].iloc[-20] * 4

        biases = detect_overconfidence(df)
        assert len(biases) > 0
        assert biases[0].bias_type == "OVERCONFIDENCE"

    def test_no_overconfidence_on_normal_volume(self):
        np.random.seed(42)
        df = _make_ohlcv(80)
        biases = detect_overconfidence(df)
        assert len(biases) == 0


class TestRecencyBias:
    def test_detects_recency_bias(self):
        np.random.seed(42)
        df = _make_ohlcv(80, trend=-0.001)
        df.iloc[-5:, df.columns.get_loc("close")] = df["close"].iloc[-5] * np.linspace(1, 1.12, 5)

        biases = detect_recency_bias(df)
        assert len(biases) > 0
        assert biases[0].bias_type == "RECENCY_BIAS"

    def test_no_recency_bias_on_consistent_trend(self):
        np.random.seed(42)
        df = _make_ohlcv(80, trend=0.001)
        biases = detect_recency_bias(df)
        assert len(biases) == 0


class TestAnchoring:
    def test_detects_anchoring_on_flat_price(self):
        np.random.seed(42)
        df = _make_ohlcv(50)
        df.iloc[-30:, df.columns.get_loc("close")] = 8000 + np.random.normal(0, 50, 30)

        biases = detect_anchoring(df)
        assert len(biases) > 0
        assert biases[0].bias_type == "ANCHORING"

    def test_no_anchoring_on_trending(self):
        np.random.seed(42)
        df = _make_ohlcv(50, trend=0.02)
        biases = detect_anchoring(df)
        assert len(biases) == 0


class TestDispositionEffect:
    def test_detects_disposition_pattern(self):
        np.random.seed(42)
        df = _make_ohlcv(40)
        gains = df["close"].pct_change()
        small_gain_mask = (gains > 0.03) & (gains < 0.05)
        df.loc[small_gain_mask, "volume"] = df["volume"] * 2
        losses_mask = gains < -0.03
        df.loc[losses_mask, "volume"] = df["volume"] * 0.5

        biases = detect_disposition_effect(df)
        if biases:
            assert biases[0].bias_type == "DISPOSITION_EFFECT"


class TestAssessBehavioralRisk:
    def test_returns_report_with_score(self):
        np.random.seed(42)
        df = _make_ohlcv(100)
        report = assess_behavioral_risk(df)
        assert isinstance(report, BehavioralRiskReport)
        assert 0 <= report.score <= 100

    def test_high_risk_on_fomo_pattern(self):
        np.random.seed(42)
        df = _make_ohlcv(60)
        df.iloc[-10:, df.columns.get_loc("close")] = df["close"].iloc[-10] * np.linspace(1, 1.6, 10)
        df.iloc[-10:, df.columns.get_loc("volume")] = df["volume"].iloc[-10] * 5

        report = assess_behavioral_risk(df)
        assert report.score > 0
        assert len(report.biases) > 0

    def test_to_dict(self):
        np.random.seed(42)
        df = _make_ohlcv(100)
        report = assess_behavioral_risk(df)
        d = report.to_dict()
        assert "score" in d
        assert "biases" in d
        assert "has_high_risk" in d

    def test_empty_biases_on_calm_market(self):
        np.random.seed(42)
        df = _make_ohlcv(100, trend=0.0005)
        report = assess_behavioral_risk(df)
        assert report.score < 30
