"""Unit tests for TechnicalAnalysisEngine."""

import numpy as np
import pandas as pd
import pytest

from trading_system.analysis.technical import TechnicalAnalysisEngine


class TestTechnicalAnalysisEngine:

    def test_compute_indicators_returns_dataframe(self, mock_ohlcv_indexed_df):
        """compute_indicators should add indicator columns."""
        engine = TechnicalAnalysisEngine()
        engine.ohlcv = mock_ohlcv_indexed_df
        df = engine.compute_indicators()

        assert "ma_20" in df.columns
        assert "ma_50" in df.columns
        assert "rsi" in df.columns
        assert "macd" in df.columns
        assert "macd_signal" in df.columns
        assert "atr_14" in df.columns
        assert "bb_upper" in df.columns
        assert "bb_lower" in df.columns
        assert "volume_sma_20" in df.columns

    def test_classify_trend_regime_uptrend(self, mock_ohlcv_indexed_df):
        """Should detect uptrend when ma20 > ma50 and close > ma20."""
        engine = TechnicalAnalysisEngine()
        engine.ohlcv = mock_ohlcv_indexed_df
        df = engine.compute_indicators()

        # Force uptrend: make last close > ma20 > ma50
        df.iloc[-1, df.columns.get_loc("close")] = df["ma_20"].iloc[-1] * 1.05
        df.iloc[-1, df.columns.get_loc("ma_20")] = df["ma_50"].iloc[-1] * 1.05

        regime = engine.classify_trend_regime(df)
        assert regime == "uptrend"

    def test_classify_trend_regime_downtrend(self, mock_ohlcv_indexed_df):
        """Should detect downtrend when ma20 < ma50 and close < ma20."""
        engine = TechnicalAnalysisEngine()
        engine.ohlcv = mock_ohlcv_indexed_df
        df = engine.compute_indicators()

        # Force downtrend: close < ma20 < ma50
        ma50_val = df["ma_50"].iloc[-1]
        if pd.isna(ma50_val):
            ma50_val = df["close"].iloc[-1]
        df.iloc[-1, df.columns.get_loc("ma_50")] = ma50_val
        df.iloc[-1, df.columns.get_loc("ma_20")] = ma50_val * 0.95
        df.iloc[-1, df.columns.get_loc("close")] = ma50_val * 0.90

        regime = engine.classify_trend_regime(df)
        assert regime == "downtrend"

    def test_rsi_range(self, mock_ohlcv_indexed_df):
        """RSI should be between 0 and 100."""
        engine = TechnicalAnalysisEngine()
        engine.ohlcv = mock_ohlcv_indexed_df
        df = engine.compute_indicators()

        rsi = df["rsi"].dropna()
        assert (rsi >= 0).all()
        assert (rsi <= 100).all()

    def test_compute_score_range(self, mock_ohlcv_indexed_df):
        """Score should be 0-100."""
        engine = TechnicalAnalysisEngine()
        engine.ohlcv = mock_ohlcv_indexed_df
        df = engine.compute_indicators()
        score, breakdown = engine.compute_score(df)

        assert 0 <= score <= 100
        assert "trend" in breakdown
        assert "rsi" in breakdown
        assert "macd" in breakdown
        assert "volatility" in breakdown
        assert "volume" in breakdown

    def test_analyze_empty_data(self):
        """Analyze with no data should return error."""
        engine = TechnicalAnalysisEngine()
        result = engine.analyze()
        assert result["status"] == "error"

    def test_volume_profile(self, mock_ohlcv_indexed_df):
        """Volume profile should return POC, VAH, VAL."""
        engine = TechnicalAnalysisEngine()
        engine.ohlcv = mock_ohlcv_indexed_df
        df = engine.compute_indicators()
        vp = engine.volume_profile(df)

        assert "poc" in vp
        assert "vah" in vp
        assert "val" in vp
        assert vp["poc"] is not None
