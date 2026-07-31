"""Alpha Validation Lab (EE, §4.1).

Raw copy from TIP/python/engines/alpha_validation.py.
Workflow for validating alpha factors before production.

Validation criteria:
- OOS performance (walk-forward)
- Parameter robustness
- Regime segmentation
- Leakage and survivorship bias tests
- Cost-adjusted returns
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

VALIDATION_VERSION = "1.0"

THRESHOLDS = {
    "min_sharpe": 0.5,
    "min_sortino": 0.7,
    "min_calmar": 0.3,
    "max_drawdown": 0.25,
    "min_hit_rate": 0.45,
    "min_oos_sharpe": 0.3,
    "min_robustness_score": 0.6,
    "max_turnover": 2.0,
}


@dataclass
class ExperimentConfig:
    experiment_id: str
    factor_name: str
    hypothesis: str
    start_date: datetime
    end_date: datetime
    train_end_date: datetime
    parameters: dict = field(default_factory=dict)
    thresholds: dict = field(default_factory=lambda: THRESHOLDS.copy())


@dataclass
class ValidationResult:
    experiment_id: str
    factor_name: str
    status: str  # VALID, WATCH, REJECT
    in_sample_metrics: dict[str, float]
    out_of_sample_metrics: dict[str, float]
    robustness_score: float
    leakage_test_passed: bool
    survivorship_test_passed: bool
    cost_adjusted_sharpe: float
    reason_codes: list[str] = field(default_factory=list)
    recommendation: str = ""
    version: str = VALIDATION_VERSION
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class AlphaValidationLab:
    """Validate alpha factors using documented thresholds."""

    def __init__(
        self,
        thresholds: dict | None = None,
        validation_version: str = VALIDATION_VERSION,
    ):
        self.thresholds = thresholds or THRESHOLDS.copy()
        self.validation_version = validation_version

    def validate(
        self,
        config: ExperimentConfig,
        in_sample_metrics: dict[str, float],
        out_of_sample_metrics: dict[str, float],
        robustness_score: float = 0.0,
        leakage_test_passed: bool = True,
        survivorship_test_passed: bool = True,
        cost_adjusted_sharpe: float = 0.0,
    ) -> ValidationResult:
        """Run validation checks and produce VALID/WATCH/REJECT decision."""
        thresholds = {**self.thresholds, **config.thresholds}
        reason_codes: list[str] = []
        failures: list[str] = []
        warnings: list[str] = []

        if not leakage_test_passed:
            failures.append("LEAKAGE_TEST_FAILED: data leakage terdeteksi — REJECT")
        if not survivorship_test_passed:
            failures.append("SURVIVORSHIP_TEST_FAILED: survivorship bias terdeteksi — REJECT")

        oos_sharpe = out_of_sample_metrics.get("sharpe", 0.0)
        if oos_sharpe < thresholds["min_oos_sharpe"]:
            failures.append(f"OOS_SHARPE_FAIL: {oos_sharpe:.4f} < {thresholds['min_oos_sharpe']}")
        else:
            reason_codes.append(f"OOS_SHARPE_PASS: {oos_sharpe:.4f}")

        is_sharpe = in_sample_metrics.get("sharpe", 0.0)
        if is_sharpe < thresholds["min_sharpe"]:
            warnings.append(f"IS_SHARPE_LOW: {is_sharpe:.4f} < {thresholds['min_sharpe']}")
        else:
            reason_codes.append(f"IS_SHARPE_PASS: {is_sharpe:.4f}")

        max_dd = in_sample_metrics.get("max_drawdown", 1.0)
        if max_dd > thresholds["max_drawdown"]:
            warnings.append(f"MAX_DRAWDOWN_HIGH: {max_dd:.4f} > {thresholds['max_drawdown']}")
        else:
            reason_codes.append(f"MAX_DRAWDOWN_PASS: {max_dd:.4f}")

        hit_rate = in_sample_metrics.get("hit_rate", 0.0)
        if hit_rate < thresholds["min_hit_rate"]:
            warnings.append(f"HIT_RATE_LOW: {hit_rate:.4f} < {thresholds['min_hit_rate']}")
        else:
            reason_codes.append(f"HIT_RATE_PASS: {hit_rate:.4f}")

        if robustness_score < thresholds["min_robustness_score"]:
            warnings.append(f"ROBUSTNESS_LOW: {robustness_score:.4f} < {thresholds['min_robustness_score']}")
        else:
            reason_codes.append(f"ROBUSTNESS_PASS: {robustness_score:.4f}")

        if cost_adjusted_sharpe < thresholds["min_sharpe"] * 0.5:
            warnings.append(f"COST_ADJUSTED_SHARPE_LOW: {cost_adjusted_sharpe:.4f}")
        else:
            reason_codes.append(f"COST_ADJUSTED_SHARPE_PASS: {cost_adjusted_sharpe:.4f}")

        if failures:
            status = "REJECT"
            recommendation = f"Faktor '{config.factor_name}' ditolak: {len(failures)} kegagalan kritis. {'; '.join(failures[:3])}"
        elif len(warnings) >= 3:
            status = "WATCH"
            recommendation = f"Faktor '{config.factor_name}' dalam pemantauan: {len(warnings)} peringatan. {'; '.join(warnings[:3])}"
        elif warnings:
            status = "WATCH"
            recommendation = f"Faktor '{config.factor_name}' dalam pemantauan: {len(warnings)} peringatan. {'; '.join(warnings[:2])}"
        else:
            status = "VALID"
            recommendation = f"Faktor '{config.factor_name}' valid untuk production. Semua tes lulus."

        reason_codes.extend(failures)
        reason_codes.extend(warnings)

        return ValidationResult(
            experiment_id=config.experiment_id,
            factor_name=config.factor_name,
            status=status,
            in_sample_metrics=in_sample_metrics,
            out_of_sample_metrics=out_of_sample_metrics,
            robustness_score=round(robustness_score, 6),
            leakage_test_passed=leakage_test_passed,
            survivorship_test_passed=survivorship_test_passed,
            cost_adjusted_sharpe=round(cost_adjusted_sharpe, 6),
            reason_codes=reason_codes,
            recommendation=recommendation,
        )

    def run_leakage_test(
        self,
        factor_dates: list[datetime],
        price_dates: list[datetime],
    ) -> bool:
        """Test for data leakage. Returns True if no leakage detected."""
        if not factor_dates or not price_dates:
            return True
        price_dates_sorted = sorted(price_dates)
        for fdate in factor_dates:
            valid_prices = [p for p in price_dates_sorted if p <= fdate]
            if not valid_prices:
                return False
        return True

    def run_survivorship_test(
        self,
        current_universe: list[str],
        historical_universe: list[str],
    ) -> bool:
        """Test for survivorship bias. Returns True if no bias detected."""
        historical_set = set(historical_universe)
        current_set = set(current_universe)
        delisted = historical_set - current_set
        if len(historical_set) > 10 and len(delisted) == 0:
            return False
        return True
