"""Unit tests for Layer 4: FF (Enhanced Risk Engine) + EE (Alpha Validation Lab)."""

import pytest
from datetime import datetime, timezone

from trading_system.risk.enhanced_risk import (
    EnhancedRiskEngine, RiskConfig, PositionSizing, RiskMetrics, RISK_VERSION,
)
from trading_system.analysis.alpha_validation import (
    AlphaValidationLab, ExperimentConfig, ValidationResult, VALIDATION_VERSION, THRESHOLDS,
)


class TestEnhancedRiskEngine:
    """Tests for FF — Enhanced Risk Engine."""

    def _make_signals(self, n=3):
        return [
            {"instrument_id": i, "symbol": f"STOCK{i}.JK", "composite_alpha": 0.8 - i * 0.1}
            for i in range(n)
        ]

    def test_size_positions_risk_on(self):
        engine = EnhancedRiskEngine()
        signals = self._make_signals()
        vols = {0: 0.20, 1: 0.25, 2: 0.30}
        prices = {0: 5000, 1: 3000, 2: 2000}
        positions = engine.size_positions(signals, 100_000_000, vols, prices, regime_state="risk_on")
        assert len(positions) > 0
        assert all(p.weight <= 0.10 for p in positions)

    def test_size_positions_crisis_max_cash(self):
        engine = EnhancedRiskEngine()
        signals = self._make_signals()
        vols = {0: 0.20, 1: 0.25, 2: 0.30}
        prices = {0: 5000, 1: 3000, 2: 2000}
        positions = engine.size_positions(signals, 100_000_000, vols, prices, regime_state="crisis")
        total_weight = sum(p.weight for p in positions)
        assert total_weight <= 0.50  # max 50% invested in crisis

    def test_size_positions_sector_cap(self):
        engine = EnhancedRiskEngine(config=RiskConfig(max_sector_pct=0.15))
        signals = self._make_signals(5)
        vols = {i: 0.20 for i in range(5)}
        prices = {i: 5000 for i in range(5)}
        sector_map = {i: "finance" for i in range(5)}
        positions = engine.size_positions(signals, 100_000_000, vols, prices, sector_map=sector_map)
        total_sector = sum(p.weight for p in positions)
        assert total_sector <= 0.15 + 0.01  # allow small rounding

    def test_compute_risk_metrics_empty(self):
        engine = EnhancedRiskEngine()
        metrics = engine.compute_risk_metrics([], 100_000_000)
        assert metrics.position_count == 0
        assert metrics.cash_allocation == 1.0

    def test_compute_risk_metrics_with_positions(self):
        engine = EnhancedRiskEngine()
        positions = [
            PositionSizing(0, "A.JK", 0.08, 100, 5000, 0.20, 0.016),
            PositionSizing(1, "B.JK", 0.05, 200, 3000, 0.25, 0.0125),
        ]
        metrics = engine.compute_risk_metrics(positions, 100_000_000)
        assert metrics.position_count == 2
        assert metrics.gross_exposure == pytest.approx(0.13, abs=0.01)
        assert metrics.cash_allocation == pytest.approx(0.87, abs=0.01)

    def test_drawdown_guard(self):
        engine = EnhancedRiskEngine()
        positions = [PositionSizing(0, "A.JK", 0.08, 100, 5000, 0.20, 0.016)]
        metrics = engine.compute_risk_metrics(positions, 100_000_000, current_drawdown=0.15)
        assert any("DRAWDOWN_GUARD" in r for r in metrics.reason_codes)

    def test_beta_guard(self):
        engine = EnhancedRiskEngine()
        positions = [
            PositionSizing(0, "A.JK", 0.50, 100, 5000, 0.20, 0.10),
            PositionSizing(1, "B.JK", 0.50, 200, 3000, 0.25, 0.125),
        ]
        betas = {0: 1.5, 1: 1.5}
        metrics = engine.compute_risk_metrics(positions, 100_000_000, betas=betas)
        assert any("BETA_GUARD" in r for r in metrics.reason_codes)

    def test_stop_loss_triggered(self):
        engine = EnhancedRiskEngine()
        positions = [PositionSizing(0, "A.JK", 0.08, 100, 5000, 0.20, 0.016)]
        stops = engine.check_stops(positions, {0: 5000}, {0: 4500})
        assert len(stops) == 1
        assert stops[0]["action"] == "STOP_LOSS"

    def test_trailing_stop_triggered(self):
        engine = EnhancedRiskEngine()
        positions = [PositionSizing(0, "A.JK", 0.08, 100, 5000, 0.20, 0.016)]
        # entry=5000, current=4600 (loss=8% = stop_loss threshold, use 4650 to be just under)
        # highest=5500, trailing_drop = (5500-4650)/5500 = 0.1545 >= 0.12
        stops = engine.check_stops(positions, {0: 5000}, {0: 4650}, {0: 5500})
        assert len(stops) == 1
        assert stops[0]["action"] == "TRAILING_STOP"

    def test_no_stop_when_profit(self):
        engine = EnhancedRiskEngine()
        positions = [PositionSizing(0, "A.JK", 0.08, 100, 5000, 0.20, 0.016)]
        stops = engine.check_stops(positions, {0: 5000}, {0: 5500}, {0: 5500})
        assert len(stops) == 0

    def test_version(self):
        assert RISK_VERSION == "1.0"


class TestAlphaValidationLab:
    """Tests for EE — Alpha Validation Lab."""

    def _make_config(self):
        return ExperimentConfig(
            experiment_id="exp_001",
            factor_name="momentum",
            hypothesis="Momentum predicts forward returns",
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2024, 1, 1),
            train_end_date=datetime(2023, 7, 1),
        )

    def test_valid_result(self):
        lab = AlphaValidationLab()
        result = lab.validate(
            config=self._make_config(),
            in_sample_metrics={"sharpe": 1.0, "max_drawdown": 0.15, "hit_rate": 0.55},
            out_of_sample_metrics={"sharpe": 0.8},
            robustness_score=0.8,
            cost_adjusted_sharpe=0.6,
        )
        assert result.status == "VALID"
        assert "valid untuk production" in result.recommendation

    def test_reject_leakage(self):
        lab = AlphaValidationLab()
        result = lab.validate(
            config=self._make_config(),
            in_sample_metrics={"sharpe": 1.0, "max_drawdown": 0.15, "hit_rate": 0.55},
            out_of_sample_metrics={"sharpe": 0.8},
            leakage_test_passed=False,
        )
        assert result.status == "REJECT"
        assert any("LEAKAGE" in r for r in result.reason_codes)

    def test_reject_survivorship(self):
        lab = AlphaValidationLab()
        result = lab.validate(
            config=self._make_config(),
            in_sample_metrics={"sharpe": 1.0, "max_drawdown": 0.15, "hit_rate": 0.55},
            out_of_sample_metrics={"sharpe": 0.8},
            survivorship_test_passed=False,
        )
        assert result.status == "REJECT"

    def test_reject_oos_sharpe(self):
        lab = AlphaValidationLab()
        result = lab.validate(
            config=self._make_config(),
            in_sample_metrics={"sharpe": 1.0, "max_drawdown": 0.15, "hit_rate": 0.55},
            out_of_sample_metrics={"sharpe": 0.1},
        )
        assert result.status == "REJECT"
        assert any("OOS_SHARPE_FAIL" in r for r in result.reason_codes)

    def test_watch_with_warnings(self):
        lab = AlphaValidationLab()
        result = lab.validate(
            config=self._make_config(),
            in_sample_metrics={"sharpe": 0.3, "max_drawdown": 0.30, "hit_rate": 0.40},
            out_of_sample_metrics={"sharpe": 0.5},
            robustness_score=0.5,
            cost_adjusted_sharpe=0.1,
        )
        assert result.status == "WATCH"

    def test_leakage_test_pass(self):
        lab = AlphaValidationLab()
        factor_dates = [datetime(2024, 1, 1), datetime(2024, 2, 1)]
        price_dates = [datetime(2023, 12, 1), datetime(2024, 1, 15), datetime(2024, 2, 15)]
        assert lab.run_leakage_test(factor_dates, price_dates) is True

    def test_leakage_test_fail(self):
        lab = AlphaValidationLab()
        factor_dates = [datetime(2024, 1, 1)]
        price_dates = [datetime(2024, 6, 1)]  # only future data
        assert lab.run_leakage_test(factor_dates, price_dates) is False

    def test_survivorship_test_pass(self):
        lab = AlphaValidationLab()
        current = ["A", "B", "C"]
        historical = ["A", "B", "C", "D", "E"]  # D and E delisted
        assert lab.run_survivorship_test(current, historical) is True

    def test_survivorship_test_fail(self):
        lab = AlphaValidationLab()
        current = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K"]
        historical = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K"]  # no delisted
        assert lab.run_survivorship_test(current, historical) is False

    def test_version(self):
        assert VALIDATION_VERSION == "1.0"

    def test_thresholds(self):
        assert "min_sharpe" in THRESHOLDS
        assert "min_oos_sharpe" in THRESHOLDS
        assert "max_drawdown" in THRESHOLDS
