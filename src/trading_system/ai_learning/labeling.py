"""Alpha-Adjusted Labeling Engine (N, §4.1).

Implements forward return labeling and triple-barrier method with
alpha-adjusted labels for ML training.

Label types:
- forward_return: simple N-day forward return
- triple_barrier: profit-take / stop-loss / time-out barriers
- alpha_adjusted: label adjusted by regime/alpha context
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class LabelingConfig:
    forward_periods: int = 5
    profit_take_pct: float = 0.05
    stop_loss_pct: float = 0.03
    max_holding_periods: int = 20
    alpha_adjust: bool = True
    regime_weights: dict[str, float] = field(default_factory=lambda: {
        "risk_on": 1.0,
        "neutral": 0.7,
        "risk_off": 0.3,
        "crisis": 0.0,
        "unknown": 0.0,
    })


def forward_return_labels(df: pd.DataFrame, periods: int = 5) -> pd.Series:
    """Compute simple forward return labels.

    Args:
        df: OHLCV DataFrame with 'close' column.
        periods: Number of periods to look forward.

    Returns:
        Series of forward returns (NaN for last `periods` rows).
    """
    return df["close"].shift(-periods) / df["close"] - 1.0


def triple_barrier_labels(
    df: pd.DataFrame,
    profit_take_pct: float = 0.05,
    stop_loss_pct: float = 0.03,
    max_periods: int = 20,
) -> pd.Series:
    """Compute triple-barrier labels.

    For each bar, determine which barrier is hit first:
    - +1: profit-take barrier hit
    - -1: stop-loss barrier hit
    - 0: time barrier hit (max holding period reached)

    Args:
        df: OHLCV DataFrame with 'high', 'low', 'close' columns.
        profit_take_pct: Profit-take threshold.
        stop_loss_pct: Stop-loss threshold.
        max_periods: Maximum holding periods before time-out.

    Returns:
        Series of labels (-1, 0, +1).
    """
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)
    labels = np.full(n, np.nan)

    for i in range(n - 1):
        entry = closes[i]
        pt = entry * (1 + profit_take_pct)
        sl = entry * (1 - stop_loss_pct)

        for j in range(i + 1, min(i + max_periods + 1, n)):
            if highs[j] >= pt:
                labels[i] = 1.0
                break
            if lows[j] <= sl:
                labels[i] = -1.0
                break
        else:
            labels[i] = 0.0

    return pd.Series(labels, index=df.index)


def alpha_adjusted_labels(
    df: pd.DataFrame,
    forward_periods: int = 5,
    regime_state: str = "neutral",
    config: LabelingConfig | None = None,
) -> pd.Series:
    """Compute alpha-adjusted labels.

    Forward returns are scaled by regime weight to account for
    market context. In risk_off/crisis, labels are dampened.

    Args:
        df: OHLCV DataFrame.
        forward_periods: N-day forward return period.
        regime_state: Current regime state.
        config: Labeling configuration.

    Returns:
        Series of alpha-adjusted labels.
    """
    config = config or LabelingConfig()
    fwd = forward_return_labels(df, forward_periods)
    weight = config.regime_weights.get(regime_state, 0.5)
    return fwd * weight


class LabelingEngine:
    """Engine for computing ML training labels."""

    def __init__(self, config: LabelingConfig | None = None):
        self.config = config or LabelingConfig()

    def compute(
        self,
        df: pd.DataFrame,
        regime_state: str = "neutral",
        non_tradeable_mask: pd.Series | None = None,
    ) -> dict[str, pd.Series]:
        """Compute all label types for a DataFrame.

        Args:
            df: OHLCV DataFrame.
            regime_state: Current regime state.
            non_tradeable_mask: Optional boolean Series (same index as df) where
                True indicates a non-tradeable bar (suspended, pre-IPO, post-delisting).
                Labels for these bars and the subsequent forward_periods bars are
                set to NaN to prevent ML from learning on non-tradeable periods.

        Returns dict with 'forward_return', 'triple_barrier', 'alpha_adjusted'.
        """
        labels = {
            "forward_return": forward_return_labels(df, self.config.forward_periods),
            "triple_barrier": triple_barrier_labels(
                df,
                self.config.profit_take_pct,
                self.config.stop_loss_pct,
                self.config.max_holding_periods,
            ),
            "alpha_adjusted": alpha_adjusted_labels(
                df, self.config.forward_periods, regime_state, self.config
            ),
        }

        if non_tradeable_mask is not None and non_tradeable_mask.any():
            fwd = self.config.forward_periods
            max_hold = self.config.max_holding_periods
            horizon = max(fwd, max_hold)
            for key, series in labels.items():
                masked = series.copy()
                idx_array = df.index
                mask_values = non_tradeable_mask.values
                for i in range(len(mask_values)):
                    if mask_values[i]:
                        end = min(i + horizon + 1, len(masked))
                        masked.iloc[i:end] = np.nan
                labels[key] = masked

        return labels
