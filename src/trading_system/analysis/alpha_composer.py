"""Alpha Composer (Y, §4.1).

Raw copy from TIP/python/engines/alpha_composer.py.
Combines factor scores with regime/sector/macro multipliers to produce
a composite alpha signal. Versioned and explainable.

Output: per-instrument composite alpha with component breakdown and reason codes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

ALPHA_VERSION = "1.0"

REGIME_MULTIPLIERS = {
    "bull": 1.0,
    "risk_on": 1.0,
    "neutral": 0.7,
    "sideways": 0.5,
    "bear": 0.2,
    "risk_off": 0.2,
    "crisis": 0.0,
    "unknown": 0.0,
}

SECTOR_MULTIPLIERS = {
    "default": 1.0,
}


@dataclass
class AlphaConfig:
    factor_weights: dict[str, float] = field(default_factory=lambda: {
        "momentum": 0.25,
        "low_volatility": 0.20,
        "quality": 0.20,
        "value": 0.15,
        "size": 0.10,
        "beta": 0.10,
    })
    regime_multiplier: dict[str, float] = field(default_factory=lambda: REGIME_MULTIPLIERS)
    sector_multiplier: dict[str, float] = field(default_factory=lambda: SECTOR_MULTIPLIERS)
    min_composite_score: float = 0.3
    min_confidence: float = 0.2


@dataclass
class AlphaSignal:
    instrument_id: int
    symbol: str
    composite_alpha: float
    regime_multiplier: float
    sector_multiplier: float
    factor_contribution: dict[str, float]
    confidence: float
    as_of: datetime
    reason_codes: list[str] = field(default_factory=list)
    version: str = ALPHA_VERSION


class AlphaComposer:
    """Compose alpha signals from factor scores, regime state, and sector context."""

    def __init__(
        self,
        config: AlphaConfig | None = None,
        alpha_version: str = ALPHA_VERSION,
        as_of: datetime | None = None,
    ):
        self.config = config or AlphaConfig()
        self.alpha_version = alpha_version
        self.as_of = as_of or datetime.now(UTC)

    def compose(
        self,
        factor_results: dict[str, Any],
        regime_state: str,
        sector_map: dict[int, str] | None = None,
    ) -> dict[str, Any]:
        """Compose alpha signals for all instruments.

        Args:
            factor_results: Output from FactorEngine.compute()
            regime_state: Current regime ("bull", "bear", "risk_on", etc.)
            sector_map: Optional mapping of instrument_id -> sector name

        Returns:
            Dict with alpha signals, composite scores, and metadata.
        """
        regime_mult = self.config.regime_multiplier.get(regime_state, 0.0)
        signals: list[AlphaSignal] = []
        reason_codes: list[str] = []

        if regime_state in ("unknown", "crisis"):
            reason_codes.append(f"REGIME_GATE: regime '{regime_state}' menghasilkan multiplier 0.0 — semua sinyal ditolak")

        composite_ranks = factor_results.get("composite_ranks", {})
        factor_list = factor_results.get("results", [])

        # Build per-instrument factor breakdown (use symbol as key since we don't have instrument_id in SQLite)
        inst_factors: dict[str, dict[str, float]] = {}
        for r in factor_list:
            if r.get("percentile_rank") is not None:
                sym = r.get("symbol", "")
                if sym not in inst_factors:
                    inst_factors[sym] = {}
                inst_factors[sym][r["factor_name"]] = r["percentile_rank"]

        for symbol, base_rank in composite_ranks.items():
            factor_contribution = {}
            weighted_sum = 0.0
            used_weight = 0.0

            inst_f = inst_factors.get(symbol, {})
            for fname, fweight in self.config.factor_weights.items():
                if fname in inst_f:
                    contribution = inst_f[fname] * fweight
                    factor_contribution[fname] = round(contribution, 6)
                    weighted_sum += contribution
                    used_weight += fweight

            if used_weight == 0:
                reason_codes.append(f"NO_FACTOR_DATA:{symbol}")
                continue

            regime_adjusted = weighted_sum * regime_mult
            sector_mult = self.config.sector_multiplier.get("default", 1.0)
            final_alpha = regime_adjusted * sector_mult
            confidence = min(base_rank * regime_mult, 1.0)

            signal = AlphaSignal(
                instrument_id=0,
                symbol=symbol,
                composite_alpha=round(final_alpha, 6),
                regime_multiplier=regime_mult,
                sector_multiplier=sector_mult,
                factor_contribution=factor_contribution,
                confidence=round(confidence, 6),
                as_of=self.as_of,
                reason_codes=[],
            )

            if final_alpha < self.config.min_composite_score:
                signal.reason_codes.append(f"LOW_ALPHA: {final_alpha:.4f} < {self.config.min_composite_score}")
            if confidence < self.config.min_confidence:
                signal.reason_codes.append(f"LOW_CONFIDENCE: {confidence:.4f} < {self.config.min_confidence}")

            signals.append(signal)

        return {
            "as_of": self.as_of,
            "alpha_version": self.alpha_version,
            "regime_state": regime_state,
            "regime_multiplier": regime_mult,
            "signals": [
                {
                    "instrument_id": s.instrument_id,
                    "symbol": s.symbol,
                    "composite_alpha": s.composite_alpha,
                    "regime_multiplier": s.regime_multiplier,
                    "sector_multiplier": s.sector_multiplier,
                    "factor_contribution": s.factor_contribution,
                    "confidence": s.confidence,
                    "reason_codes": s.reason_codes,
                }
                for s in signals
            ],
            "reason_codes": reason_codes,
        }
