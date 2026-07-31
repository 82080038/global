"""Unit tests for Component W: World Monitor patterns (7-signal + CII)."""

import pytest

from trading_system.analysis.world_monitor import (
    CII_COUNTRY_WEIGHTS,
    MarketSignal,
    compute_cii_score,
    compute_market_composite,
    detect_convergence,
    detect_sector_cascade,
    detect_silent_divergence,
    detect_velocity_spike,
    get_country_weight,
)


class TestCIIWeights:
    def test_known_country(self):
        w = get_country_weight("US")
        assert w["baseline_risk"] == 5
        assert w["event_multiplier"] == 0.3

    def test_unknown_country_default(self):
        w = get_country_weight("XX")
        assert w["baseline_risk"] == 15
        assert w["event_multiplier"] == 1.0

    def test_case_insensitive(self):
        w = get_country_weight("us")
        assert w["baseline_risk"] == 5

    def test_id_in_weights(self):
        assert "ID" in CII_COUNTRY_WEIGHTS


class TestCIIScoring:
    def test_zero_components(self):
        score = compute_cii_score("US", unrest=0, conflict=0, security=0, information=0)
        assert score.combined_score == 5 * 0.4  # baseline * 0.4

    def test_max_components(self):
        score = compute_cii_score("US", unrest=100, conflict=100, security=100, information=100)
        # US has multiplier 0.3, so components are 30,30,30,100
        event = 30 * 0.25 + 30 * 0.30 + 30 * 0.20 + 100 * 0.25
        expected = 5 * 0.4 + event * 0.6
        assert abs(score.combined_score - expected) < 0.1

    def test_event_multiplier_applied(self):
        score_id = compute_cii_score("ID", unrest=50)
        score_us = compute_cii_score("US", unrest=50)
        # ID has multiplier 0.8, US has 0.3
        assert score_id.components.unrest == 50 * 0.8
        assert score_us.components.unrest == 50 * 0.3

    def test_boosts_added(self):
        score_no_boost = compute_cii_score("US", unrest=20)
        score_with_boost = compute_cii_score("US", unrest=20, boosts={"earthquake": 25})
        assert score_with_boost.combined_score > score_no_boost.combined_score

    def test_boost_capped(self):
        score = compute_cii_score("US", boosts={"earthquake": 100})
        # earthquake cap is 25
        base = 5 * 0.4
        assert score.combined_score <= base + 25

    def test_score_capped_at_100(self):
        score = compute_cii_score("UA", unrest=100, conflict=100, security=100, information=100,
                                  boosts={"earthquake": 25, "sanctions": 14, "advisory": 15})
        assert score.combined_score <= 100

    def test_components_capped(self):
        score = compute_cii_score("KP", unrest=200)
        assert score.components.unrest <= 100

    def test_trend_default(self):
        score = compute_cii_score("US")
        assert score.trend == "stable"

    def test_methodology_version(self):
        score = compute_cii_score("US")
        assert "v1" in score.methodology_version


class TestConvergenceDetection:
    def test_convergence_detected(self):
        news = [
            {"source_type": "wire", "timestamp": "2024-01-01T10:00:00Z", "title": "Event A"},
            {"source_type": "government", "timestamp": "2024-01-01T10:10:00Z", "title": "Event A"},
            {"source_type": "intel", "timestamp": "2024-01-01T10:15:00Z", "title": "Event A"},
        ]
        signals = detect_convergence(news, window_minutes=30, min_sources=3)
        assert len(signals) > 0
        assert signals[0].signal_type == "convergence"

    def test_no_convergence_insufficient_sources(self):
        news = [
            {"source_type": "wire", "timestamp": "2024-01-01T10:00:00Z"},
            {"source_type": "wire", "timestamp": "2024-01-01T10:10:00Z"},
        ]
        signals = detect_convergence(news, min_sources=3)
        assert len(signals) == 0


class TestVelocitySpike:
    def test_spike_detected(self):
        counts = [5, 5, 5, 15]
        signals = detect_velocity_spike(counts)
        assert len(signals) > 0
        assert signals[0].signal_type == "velocity_spike"

    def test_no_spike(self):
        counts = [5, 5, 5, 6]
        signals = detect_velocity_spike(counts)
        assert len(signals) == 0

    def test_high_severity(self):
        counts = [5, 5, 5, 30]
        signals = detect_velocity_spike(counts)
        assert any(s.severity == "high" for s in signals)


class TestSilentDivergence:
    def test_divergence_detected(self):
        moves = [{"ticker": "BBCA.JK", "change_pct": 3.5}]
        signals = detect_silent_divergence(moves, news_count=0)
        assert len(signals) == 1
        assert signals[0].signal_type == "silent_divergence"

    def test_no_divergence_with_news(self):
        moves = [{"ticker": "BBCA.JK", "change_pct": 3.5}]
        signals = detect_silent_divergence(moves, news_count=5)
        assert len(signals) == 0

    def test_no_divergence_small_move(self):
        moves = [{"ticker": "BBCA.JK", "change_pct": 1.0}]
        signals = detect_silent_divergence(moves, news_count=0)
        assert len(signals) == 0


class TestSectorCascade:
    def test_upward_cascade(self):
        sectors = {"tech": 2.5, "finance": 2.0, "consumer": 1.8, "energy": 0.5}
        signals = detect_sector_cascade(sectors, min_sectors=3)
        assert len(signals) == 1
        assert "cascade UP" in signals[0].title

    def test_downward_cascade(self):
        sectors = {"tech": -2.5, "finance": -2.0, "consumer": -1.8, "energy": 0.5}
        signals = detect_sector_cascade(sectors, min_sectors=3)
        assert len(signals) == 1
        assert "cascade DOWN" in signals[0].title

    def test_no_cascade(self):
        sectors = {"tech": 0.5, "finance": -0.3, "consumer": 0.2}
        signals = detect_sector_cascade(sectors, min_sectors=3)
        assert len(signals) == 0


class TestMarketComposite:
    def test_empty_inputs(self):
        result = compute_market_composite()
        assert result["total_signals"] == 0
        assert result["composite_score"] == 0

    def test_with_all_inputs(self):
        result = compute_market_composite(
            news_items=[
                {"source_type": "wire", "timestamp": "2024-01-01T10:00:00Z"},
                {"source_type": "gov", "timestamp": "2024-01-01T10:05:00Z"},
                {"source_type": "intel", "timestamp": "2024-01-01T10:10:00Z"},
            ],
            mention_counts=[5, 5, 5, 20],
            market_moves=[{"ticker": "TEST.JK", "change_pct": 3.0}],
            sector_moves={"tech": 2.5, "finance": 2.0, "consumer": 1.8},
            news_count=0,
        )
        assert result["total_signals"] > 0
        assert result["composite_score"] > 0
        assert "by_type" in result
        assert "signals" in result

    def test_composite_score_capped(self):
        # Generate many signals
        big_sector = {f"s{i}": 5.0 for i in range(20)}
        result = compute_market_composite(sector_moves=big_sector)
        assert result["composite_score"] <= 100
