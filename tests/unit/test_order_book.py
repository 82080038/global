"""Unit tests for Component U: Order Book Analyzer."""

import numpy as np
import pandas as pd
import pytest

from trading_system.analysis.order_book import OrderBookAnalyzer


@pytest.fixture
def sample_data():
    """Create sample OHLCV data with deliberate gaps."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=100, freq="D")
    prices = [100.0]
    for i in range(1, 100):
        if i % 10 == 0:
            gap = np.random.choice([-0.05, 0.05])
            new_price = prices[-1] * (1 + gap)
        else:
            change = np.random.normal(0, 0.02)
            new_price = prices[-1] * (1 + change)
        prices.append(float(new_price))

    volumes = np.random.randint(1000, 10000, 100).astype(float)
    return pd.DataFrame({
        "date": dates,
        "close": prices,
        "high": [p * 1.01 for p in prices],
        "low": [p * 0.99 for p in prices],
        "volume": volumes,
    })


@pytest.fixture
def no_gap_data():
    """Create data with no gaps."""
    dates = pd.date_range("2024-01-01", periods=50, freq="D")
    prices = [100 + i * 0.1 for i in range(50)]
    volumes = [5000.0] * 50
    return pd.DataFrame({
        "date": dates,
        "close": prices,
        "high": [p * 1.01 for p in prices],
        "low": [p * 0.99 for p in prices],
        "volume": volumes,
    })


class TestPriceGapDetection:
    def test_detect_price_gaps(self, sample_data):
        analyzer = OrderBookAnalyzer(gap_threshold=0.02)
        gaps = analyzer.detect_price_gaps(sample_data)
        assert len(gaps) > 0
        for g in gaps:
            assert g["gap_ratio"] > 0.02
            assert g["direction"] in ("UP", "DOWN")

    def test_no_gaps(self, no_gap_data):
        analyzer = OrderBookAnalyzer(gap_threshold=0.02)
        gaps = analyzer.detect_price_gaps(no_gap_data)
        assert len(gaps) == 0

    def test_gap_direction(self, sample_data):
        analyzer = OrderBookAnalyzer(gap_threshold=0.02)
        gaps = analyzer.detect_price_gaps(sample_data)
        up_gaps = [g for g in gaps if g["direction"] == "UP"]
        down_gaps = [g for g in gaps if g["direction"] == "DOWN"]
        assert len(up_gaps) > 0 or len(down_gaps) > 0


class TestVolumeGapDetection:
    def test_detect_volume_gaps(self, sample_data):
        analyzer = OrderBookAnalyzer(volume_threshold=0.5)
        gaps = analyzer.detect_volume_gaps(sample_data)
        assert len(gaps) > 0
        for g in gaps:
            assert g["volume_gap_ratio"] > 0.5

    def test_no_volume_gaps(self, no_gap_data):
        analyzer = OrderBookAnalyzer(volume_threshold=0.5)
        gaps = analyzer.detect_volume_gaps(no_gap_data)
        assert len(gaps) == 0


class TestSupportResistance:
    def test_identify_levels(self, sample_data):
        analyzer = OrderBookAnalyzer()
        levels = analyzer.identify_support_resistance_levels(sample_data, window=10)
        assert "support_levels" in levels
        assert "resistance_levels" in levels
        assert isinstance(levels["support_levels"], list)
        assert isinstance(levels["resistance_levels"], list)

    def test_levels_have_strength(self, sample_data):
        analyzer = OrderBookAnalyzer()
        levels = analyzer.identify_support_resistance_levels(sample_data, window=10)
        for sl in levels["support_levels"]:
            assert "level" in sl
            assert "touches" in sl
            assert "strength" in sl
            assert sl["touches"] >= 3

    def test_max_10_levels(self, sample_data):
        analyzer = OrderBookAnalyzer()
        levels = analyzer.identify_support_resistance_levels(sample_data, window=10)
        assert len(levels["support_levels"]) <= 10
        assert len(levels["resistance_levels"]) <= 10


class TestMarketEfficiency:
    def test_efficiency_range(self, sample_data):
        analyzer = OrderBookAnalyzer()
        score = analyzer.calculate_market_efficiency(sample_data)
        assert 0 <= score <= 1

    def test_efficiency_detailed(self, sample_data):
        analyzer = OrderBookAnalyzer()
        result = analyzer.analyze_market_efficiency(sample_data)
        assert "efficiency_score" in result
        assert "volatility" in result
        assert "gap_frequency" in result
        assert 0 <= result["efficiency_score"] <= 1


class TestSignals:
    def test_signal_structure(self, sample_data):
        analyzer = OrderBookAnalyzer()
        gaps = analyzer.detect_price_gaps(sample_data)
        vgaps = analyzer.detect_volume_gaps(sample_data)
        levels = analyzer.identify_support_resistance_levels(sample_data)
        signals = analyzer.generate_order_book_signals(sample_data, gaps, vgaps, levels)
        assert signals["signal"] in ("BUY", "SELL", "HOLD")
        assert 0 <= signals["confidence"] <= 1
        assert "reason" in signals


class TestComprehensiveAnalysis:
    def test_comprehensive(self, sample_data):
        analyzer = OrderBookAnalyzer()
        result = analyzer.comprehensive_analysis(sample_data)
        assert "price_gaps" in result
        assert "volume_gaps" in result
        assert "support_levels" in result
        assert "resistance_levels" in result
        assert "market_efficiency" in result
        assert "patterns" in result
        assert "probabilities" in result
        assert "gap_predictions" in result
        assert "summary" in result
        assert result["summary"]["total_gaps"] >= 0

    def test_analyze_order_book(self, sample_data):
        analyzer = OrderBookAnalyzer()
        result = analyzer.analyze_order_book(sample_data)
        assert "gap_count" in result
        assert "efficiency_score" in result
        assert "signals" in result
        assert "analysis_timestamp" in result

    def test_empty_data(self):
        analyzer = OrderBookAnalyzer()
        empty = pd.DataFrame(columns=["close", "high", "low", "volume"])
        result = analyzer.analyze_order_book(empty)
        assert "error" in result or result["gap_count"] == 0


class TestGapFillPredictions:
    def test_predictions_with_gaps(self, sample_data):
        analyzer = OrderBookAnalyzer()
        preds = analyzer.generate_gap_fill_predictions(sample_data)
        for p in preds:
            assert p["type"] in ("GAP_FILL_UP", "GAP_FILL_DOWN")
            assert "target_price" in p
            assert "probability" in p
            assert 0 <= p["probability"] <= 1

    def test_no_predictions_without_gaps(self, no_gap_data):
        analyzer = OrderBookAnalyzer(gap_threshold=0.02)
        preds = analyzer.generate_gap_fill_predictions(no_gap_data)
        assert len(preds) == 0


class TestPatternProbability:
    def test_pattern_probability(self, sample_data):
        analyzer = OrderBookAnalyzer()
        result = analyzer.calculate_pattern_probability(sample_data, lookback=30)
        assert "pattern_probability" in result
        assert "total_patterns" in result
        assert 0 <= result["pattern_probability"] <= 1
