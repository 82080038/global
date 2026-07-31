"""Market regime detection — adaptasi dari pasar_modal/src/trading/regime.py.

Mendeteksi regime pasar berdasarkan VIX, IHSG vs SMA200, dan korelasi.
"""

from __future__ import annotations

from typing import Literal

Regime = Literal["trending", "neutral", "volatile", "shock"]

REGIME_MULTIPLIERS: dict[Regime, float] = {
    "trending": 1.0,
    "neutral": 0.7,
    "volatile": 0.3,
    "shock": 0.0,
}


def detect_regime(
    vix: float,
    ihsg_close: float,
    ihsg_sma_200: float,
    avg_correlation: float,
) -> Regime:
    """Detect market regime based on simple rule-based logic.

    Args:
        vix: VIX index level.
        ihsg_close: Latest IHSG close price.
        ihsg_sma_200: IHSG 200-day simple moving average.
        avg_correlation: Average pairwise correlation among universe stocks.

    Returns:
        One of 'trending', 'neutral', 'volatile', 'shock'.
    """
    if vix > 35:
        return "shock"
    if vix > 25:
        return "volatile"
    if ihsg_close > ihsg_sma_200 and avg_correlation < 0.6:
        return "trending"
    return "neutral"


def regime_to_multiplier(regime: Regime) -> float:
    """Konversi regime ke multiplier untuk position sizing."""
    return REGIME_MULTIPLIERS.get(regime, 0.5)
