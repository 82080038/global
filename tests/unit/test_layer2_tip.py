"""Unit tests for Layer 2: K (Advanced Technical) + F (Enhanced Regime) + X (Factor Engine)."""

import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from trading_system.analysis.advanced_technical import (
    ichimoku_cloud, williams_r, on_balance_volume, stochastic_rsi, compute_advanced_indicators,
)
from trading_system.analysis.enhanced_regime import EnhancedRegimeEngine
from trading_system.analysis.factor_engine import (
    FactorEngine, FactorConfig, percentile_rank,
    compute_momentum, compute_low_volatility, compute_quality, compute_size, compute_value_proxy,
)


def _make_ohlcv(n=250, start_price=1000):
    dates = pd.bdate_range(start="2024-01-01", periods=n)
    rng = np.random.RandomState(42)
    returns = rng.normal(0.001, 0.015, n)
    close = start_price * np.cumprod(1 + returns)
    high = close * (1 + np.abs(rng.normal(0, 0.01, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.01, n)))
    open_ = np.roll(close, 1)
    open_[0] = start_price
    volume = rng.randint(1_000_000, 50_000_000, n).astype(float)
    return pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close,
        "volume": volume, "adjusted_close": close,
    }, index=dates)


class TestAdvancedTechnical:
    """Tests for K — Advanced Technical Indicators."""

    def test_ichimoku_cloud(self):
        df = _make_ohlcv(100)
        result = ichimoku_cloud(df)
        assert "tenkan_sen" in result.columns
        assert "kijun_sen" in result.columns
        assert "senkou_span_a" in result.columns
        assert "senkou_span_b" in result.columns
        assert "chikou_span" in result.columns
        assert len(result) == 100

    def test_williams_r(self):
        df = _make_ohlcv(100)
        wr = williams_r(df, period=14)
        assert len(wr) == 100
        assert wr.min() >= -100
        assert wr.max() <= 0

    def test_on_balance_volume(self):
        df = _make_ohlcv(100)
        obv = on_balance_volume(df)
        assert len(obv) == 100
        assert obv.iloc[0] == 0 or obv.iloc[0] == df["volume"].iloc[0]

    def test_stochastic_rsi(self):
        df = _make_ohlcv(100)
        sr = stochastic_rsi(df)
        assert len(sr) == 100
        assert sr.min() >= 0
        assert sr.max() <= 1

    def test_compute_advanced_indicators(self):
        df = _make_ohlcv(100)
        result = compute_advanced_indicators(df)
        assert "ichimoku_tenkan_sen" in result.columns
        assert "williams_r" in result.columns
        assert "obv" in result.columns
        assert "stoch_rsi" in result.columns

    def test_williams_r_short_df(self):
        df = _make_ohlcv(5)
        wr = williams_r(df, period=14)
        assert len(wr) == 5
        assert wr.isna().sum() <= 5  # all NaN expected for short data


class TestEnhancedRegime:
    """Tests for F — Enhanced Regime Engine."""

    def test_compute_with_no_data(self):
        storage = MagicMock()
        storage.load_ohlcv.return_value = pd.DataFrame()
        engine = EnhancedRegimeEngine(storage=storage)
        result = engine.compute()
        assert result["regime"] == "unknown"
        assert result["confidence"] == 0.0

    def test_compute_risk_on(self):
        storage = MagicMock()
        df = _make_ohlcv(100)
        df.index = pd.bdate_range(start=datetime.now() - timedelta(days=100), periods=100)
        storage.load_ohlcv.return_value = df
        engine = EnhancedRegimeEngine(storage=storage)
        result = engine.compute()
        assert result["regime"] in ("risk_on", "risk_off", "neutral", "unknown")
        assert "config_version" in result
        assert "feature_snapshot" in result

    def test_stale_data_detected(self):
        storage = MagicMock()
        df = _make_ohlcv(100)
        df.index = pd.bdate_range(start="2020-01-01", periods=100)
        storage.load_ohlcv.return_value = df
        engine = EnhancedRegimeEngine(storage=storage)
        result = engine.compute()
        assert result["regime"] == "unknown"
        assert any("STALE_DATA" in r for r in result["metadata"]["reason_codes"])

    def test_config_version(self):
        engine = EnhancedRegimeEngine()
        assert engine.config_version == "2.0"

    def test_default_config_has_weights(self):
        engine = EnhancedRegimeEngine()
        total_weight = sum(c["weight"] for c in engine.config)
        assert abs(total_weight - 1.0) < 0.01


class TestFactorEngine:
    """Tests for X — Factor Engine."""

    def test_percentile_rank(self):
        vals = np.array([1, 2, 3, 4, 5])
        assert percentile_rank(vals, 1) == 0.1
        assert percentile_rank(vals, 5) == 0.9
        assert percentile_rank(vals, 3) == 0.5

    def test_percentile_rank_empty(self):
        assert percentile_rank(np.array([]), 1) == 0.5

    def test_compute_momentum(self):
        df = _make_ohlcv(260)
        val, bars = compute_momentum(df, datetime.now(timezone.utc))
        assert val is not None
        assert bars == 260

    def test_compute_momentum_short(self):
        df = _make_ohlcv(10)
        val, bars = compute_momentum(df, datetime.now(timezone.utc))
        assert val is None

    def test_compute_low_volatility(self):
        df = _make_ohlcv(100)
        val, bars = compute_low_volatility(df, datetime.now(timezone.utc))
        assert val is not None
        assert val < 0  # negative vol

    def test_compute_quality(self):
        df = _make_ohlcv(100)
        val, bars = compute_quality(df, datetime.now(timezone.utc))
        assert val is not None

    def test_compute_size(self):
        df = _make_ohlcv(25)
        val, bars = compute_size(df, datetime.now(timezone.utc))
        assert val is not None
        assert val > 0

    def test_compute_value_proxy(self):
        df = _make_ohlcv(10)
        val, bars = compute_value_proxy(df, datetime.now(timezone.utc))
        assert val is not None
        assert val > 0

    def test_factor_engine_compute(self):
        storage = MagicMock()
        df = _make_ohlcv(260)
        df.index = pd.bdate_range(start=datetime.now() - timedelta(days=260), periods=260)
        storage.load_ohlcv.return_value = df
        storage.list_tickers.return_value = ["TEST.JK", "ABC.JK"]

        engine = FactorEngine(storage=storage)
        result = engine.compute(tickers=["TEST.JK", "ABC.JK"])

        assert "as_of" in result
        assert "factor_version" in result
        assert "composite_ranks" in result
        assert "results" in result
        assert result["universe_size"] == 2

    def test_factor_engine_insufficient_history(self):
        storage = MagicMock()
        df = _make_ohlcv(10)
        storage.load_ohlcv.return_value = df
        storage.list_tickers.return_value = ["TEST.JK"]

        engine = FactorEngine(storage=storage)
        result = engine.compute(tickers=["TEST.JK"])
        assert result["skipped_history"] >= 1

    def test_factor_config(self):
        cfg = FactorConfig("momentum", weight=2.0)
        assert cfg.name == "momentum"
        assert cfg.weight == 2.0
        assert cfg.enabled is True
