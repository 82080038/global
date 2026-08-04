"""Unit tests for Layer 3: Y (Alpha Composer) + Z (No-Trade Engine)."""

from datetime import UTC, datetime

from trading_system.analysis.alpha_composer import (
    ALPHA_VERSION,
    REGIME_MULTIPLIERS,
    AlphaComposer,
    AlphaConfig,
)
from trading_system.analysis.no_trade import (
    NOTRADE_VERSION,
    NoTradeEngine,
)


class TestAlphaComposer:
    """Tests for Y — Alpha Composer."""

    def _make_factor_results(self):
        return {
            "composite_ranks": {"TEST.JK": 0.8, "ABC.JK": 0.5},
            "results": [
                {"symbol": "TEST.JK", "factor_name": "momentum", "percentile_rank": 0.9, "raw_value": 0.15},
                {"symbol": "TEST.JK", "factor_name": "low_volatility", "percentile_rank": 0.7, "raw_value": -0.02},
                {"symbol": "TEST.JK", "factor_name": "quality", "percentile_rank": 0.8, "raw_value": 1.2},
                {"symbol": "ABC.JK", "factor_name": "momentum", "percentile_rank": 0.4, "raw_value": 0.05},
                {"symbol": "ABC.JK", "factor_name": "low_volatility", "percentile_rank": 0.6, "raw_value": -0.03},
            ],
        }

    def test_compose_risk_on(self):
        composer = AlphaComposer()
        result = composer.compose(self._make_factor_results(), regime_state="risk_on")
        assert result["regime_state"] == "risk_on"
        assert result["regime_multiplier"] == 1.0
        assert len(result["signals"]) == 2
        assert result["alpha_version"] == ALPHA_VERSION

    def test_compose_crisis_blocks_all(self):
        composer = AlphaComposer()
        result = composer.compose(self._make_factor_results(), regime_state="crisis")
        assert result["regime_multiplier"] == 0.0
        for signal in result["signals"]:
            assert signal["composite_alpha"] == 0.0
        assert any("REGIME_GATE" in r for r in result["reason_codes"])

    def test_compose_unknown_blocks_all(self):
        composer = AlphaComposer()
        result = composer.compose(self._make_factor_results(), regime_state="unknown")
        assert result["regime_multiplier"] == 0.0

    def test_compose_neutral_scales_down(self):
        composer = AlphaComposer()
        result = composer.compose(self._make_factor_results(), regime_state="neutral")
        assert result["regime_multiplier"] == 0.7

    def test_low_alpha_flagged(self):
        config = AlphaConfig(min_composite_score=0.99)
        composer = AlphaComposer(config=config)
        result = composer.compose(self._make_factor_results(), regime_state="risk_on")
        for signal in result["signals"]:
            assert any("LOW_ALPHA" in r for r in signal["reason_codes"])

    def test_low_confidence_flagged(self):
        config = AlphaConfig(min_confidence=0.99)
        composer = AlphaComposer(config=config)
        result = composer.compose(self._make_factor_results(), regime_state="risk_on")
        for signal in result["signals"]:
            assert any("LOW_CONFIDENCE" in r for r in signal["reason_codes"])

    def test_regime_multipliers_complete(self):
        for regime in ["bull", "risk_on", "neutral", "sideways", "bear", "risk_off", "crisis", "unknown"]:
            assert regime in REGIME_MULTIPLIERS

    def test_factor_weights_sum_to_one(self):
        config = AlphaConfig()
        total = sum(config.factor_weights.values())
        assert abs(total - 1.0) < 0.01

    def test_no_factor_data(self):
        results = {"composite_ranks": {"XYZ.JK": 0.5}, "results": []}
        composer = AlphaComposer()
        result = composer.compose(results, regime_state="risk_on")
        assert any("NO_FACTOR_DATA" in r for r in result["reason_codes"])
        assert len(result["signals"]) == 0


class TestNoTradeEngine:
    """Tests for Z — No-Trade Engine."""

    def _make_signal(self, confidence=0.5, composite_alpha=0.5, symbol="TEST.JK"):
        return {"instrument_id": 1, "symbol": symbol, "confidence": confidence, "composite_alpha": composite_alpha}

    def test_proceed_when_all_gates_pass(self):
        engine = NoTradeEngine()
        result = engine.evaluate(
            alpha_signal=self._make_signal(),
            regime_state="risk_on",
            liquidity_volume=500_000,
            bars_history=100,
        )
        assert result.decision == "PROCEED"
        assert len(result.gates_failed) == 0

    def test_no_trade_regime_blocked(self):
        engine = NoTradeEngine()
        result = engine.evaluate(
            alpha_signal=self._make_signal(),
            regime_state="crisis",
        )
        assert result.decision == "NO_TRADE"
        assert "REGIME_BLOCKED" in result.gates_failed

    def test_no_trade_unknown_regime(self):
        engine = NoTradeEngine()
        result = engine.evaluate(
            alpha_signal=self._make_signal(),
            regime_state="unknown",
        )
        assert result.decision == "NO_TRADE"
        assert "REGIME_BLOCKED" in result.gates_failed

    def test_no_trade_low_confidence(self):
        engine = NoTradeEngine()
        result = engine.evaluate(
            alpha_signal=self._make_signal(confidence=0.1),
            regime_state="risk_on",
        )
        assert result.decision == "NO_TRADE"
        assert "LOW_CONFIDENCE" in result.gates_failed

    def test_no_trade_low_alpha(self):
        engine = NoTradeEngine()
        result = engine.evaluate(
            alpha_signal=self._make_signal(composite_alpha=0.1),
            regime_state="risk_on",
        )
        assert result.decision == "NO_TRADE"
        assert "LOW_ALPHA" in result.gates_failed

    def test_no_trade_low_liquidity(self):
        engine = NoTradeEngine()
        result = engine.evaluate(
            alpha_signal=self._make_signal(),
            regime_state="risk_on",
            liquidity_volume=50_000,
        )
        assert result.decision == "NO_TRADE"
        assert "LOW_LIQUIDITY" in result.gates_failed

    def test_no_trade_insufficient_history(self):
        engine = NoTradeEngine()
        result = engine.evaluate(
            alpha_signal=self._make_signal(),
            regime_state="risk_on",
            bars_history=30,
        )
        assert result.decision == "NO_TRADE"
        assert "INSUFFICIENT_HISTORY" in result.gates_failed

    def test_no_trade_stale_data(self):
        engine = NoTradeEngine()
        old_date = datetime(2020, 1, 1, tzinfo=UTC)
        result = engine.evaluate(
            alpha_signal=self._make_signal(),
            regime_state="risk_on",
            latest_data_date=old_date,
        )
        assert result.decision == "NO_TRADE"
        assert "STALE_DATA" in result.gates_failed

    def test_no_trade_event_risk(self):
        engine = NoTradeEngine()
        result = engine.evaluate(
            alpha_signal=self._make_signal(),
            regime_state="risk_on",
            event_risk=True,
        )
        assert result.decision == "NO_TRADE"
        assert "EVENT_RISK" in result.gates_failed

    def test_no_trade_model_disagreement(self):
        engine = NoTradeEngine()
        result = engine.evaluate(
            alpha_signal=self._make_signal(),
            regime_state="risk_on",
            model_agreement=0.3,
        )
        assert result.decision == "NO_TRADE"
        assert "MODEL_DISAGREEMENT" in result.gates_failed

    def test_no_trade_data_quality_fail(self):
        engine = NoTradeEngine()
        result = engine.evaluate(
            alpha_signal=self._make_signal(),
            regime_state="risk_on",
            data_quality={"passed": False, "issues": ["zero prices"]},
        )
        assert result.decision == "NO_TRADE"
        assert "DATA_QUALITY_FAIL" in result.gates_failed

    def test_batch_evaluate(self):
        engine = NoTradeEngine()
        signals = [
            self._make_signal(confidence=0.5, composite_alpha=0.5, symbol="A"),
            self._make_signal(confidence=0.1, composite_alpha=0.5, symbol="B"),
        ]
        results = engine.evaluate_batch(signals, regime_state="risk_on")
        assert len(results) == 2
        assert results[0].decision == "PROCEED"
        assert results[1].decision == "NO_TRADE"

    def test_version(self):
        assert NOTRADE_VERSION == "1.1"
