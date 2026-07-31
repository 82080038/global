"""Tests for SentimentEngine — aggregation and fallback logic."""

import pandas as pd
from unittest.mock import MagicMock, patch

from trading_system.sentiment.engine import SentimentEngine


def test_sentiment_engine_name():
    engine = SentimentEngine(storage=MagicMock())
    assert engine.name == "sentiment"


def test_sentiment_no_ohlcv():
    storage = MagicMock()
    storage.load_ohlcv.return_value = pd.DataFrame()
    engine = SentimentEngine(storage=storage)
    result = engine.compute("BBCA.JK")
    assert result["status"] == "error"


def test_sentiment_proxy_fallback():
    """When all sub-sources return None, should fall back to price/volume proxy."""
    storage = MagicMock()
    df = pd.DataFrame({
        "close": [8000, 8050, 8100, 8150, 8200] * 10,
        "volume": [10_000_000] * 50,
        "high": [8100, 8150, 8200, 8250, 8300] * 10,
        "low": [7900, 7950, 8000, 8050, 8100] * 10,
    }, index=pd.date_range("2024-01-01", periods=50, freq="B"))
    storage.load_ohlcv.return_value = df

    engine = SentimentEngine(storage=storage)

    # Patch all sub-sources to return None
    with patch("trading_system.sentiment.foreign_flow.ForeignFlowSentiment.compute", return_value=None), \
         patch("trading_system.sentiment.broker_summary.BrokerSummarySentiment.compute", return_value=None), \
         patch("trading_system.sentiment.social_media.SocialMediaSentiment.compute", return_value=None), \
         patch("trading_system.sentiment.google_trends.GoogleTrendsSentiment.compute", return_value=None), \
         patch.object(engine, "_news_sentiment", return_value=None):
        result = engine.compute("BBCA.JK")
        assert result["status"] == "ok"
        assert "score" in result
        assert result["breakdown"]["source"] == "price_volume_proxy"
        assert "note" in result["breakdown"]


def test_sentiment_with_foreign_flow():
    """When foreign_flow returns a result, it should be included in aggregation."""
    storage = MagicMock()
    df = pd.DataFrame({
        "close": [8000, 8050, 8100, 8150, 8200] * 10,
        "volume": [10_000_000] * 50,
        "high": [8100, 8150, 8200, 8250, 8300] * 10,
        "low": [7900, 7950, 8000, 8050, 8100] * 10,
    }, index=pd.date_range("2024-01-01", periods=50, freq="B"))
    storage.load_ohlcv.return_value = df

    engine = SentimentEngine(storage=storage)

    # Patch sub-sources: foreign_flow returns data, others return None
    with patch("trading_system.sentiment.foreign_flow.ForeignFlowSentiment.compute", return_value={
        "score": 65.0, "sentiment": 0.3, "signal": "foreign_accumulation", "detail": {}
    }), patch("trading_system.sentiment.broker_summary.BrokerSummarySentiment.compute", return_value=None), \
         patch("trading_system.sentiment.social_media.SocialMediaSentiment.compute", return_value=None), \
         patch("trading_system.sentiment.google_trends.GoogleTrendsSentiment.compute", return_value=None), \
         patch.object(engine, "_news_sentiment", return_value=None):
        result = engine.compute("BBCA.JK")
        assert result["status"] == "ok"
        assert "foreign_flow" in result["breakdown"]["sources"]
        assert result["breakdown"]["active_sources"] == ["foreign_flow"]
