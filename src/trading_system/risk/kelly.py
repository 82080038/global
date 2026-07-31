"""Kelly Criterion position sizing — adaptasi dari pasar_modal/src/trading/kelly_criterion.py.

Reference: PASAR_MODAL_KNOWLEDGE_BASE.md Section 9.5
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class KellyResult:
    """Hasil perhitungan Kelly Criterion."""

    kelly_fraction: float
    expected_return: float
    win_rate: float
    avg_win: float
    avg_loss: float
    half_kelly: float
    quarter_kelly: float


def calculate_kelly_criterion(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
) -> KellyResult:
    """Hitung Kelly Criterion fraction.

    Formula: f* = (bp - q) / b
    where:
    - b = avg_win / avg_loss (odds)
    - p = win_rate
    - q = 1 - win_rate
    """
    if avg_loss <= 0:
        raise ValueError("Average loss must be positive")

    b = avg_win / avg_loss
    p = win_rate
    q = 1 - p

    kelly_fraction = (b * p - q) / b
    kelly_fraction = max(0, kelly_fraction)
    kelly_fraction = min(kelly_fraction, 1.0)

    expected_return = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

    return KellyResult(
        kelly_fraction=kelly_fraction,
        expected_return=expected_return,
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        half_kelly=kelly_fraction / 2,
        quarter_kelly=kelly_fraction / 4,
    )


def calculate_position_size_kelly(
    capital: float,
    kelly_fraction: float,
    entry_price: float,
    stop_loss: float | None = None,
    max_position_pct: float = 0.25,
) -> dict:
    """Hitung position size berdasarkan Kelly Criterion.

    Args:
        capital: Total capital.
        kelly_fraction: Kelly fraction (0-1).
        entry_price: Entry price per share.
        stop_loss: Stop loss price. Optional.
        max_position_pct: Maximum position as percentage of capital. Default 25%.

    Returns:
        Dictionary dengan position size details.
    """
    position_value = capital * kelly_fraction
    max_position_value = capital * max_position_pct
    position_value = min(position_value, max_position_value)

    if entry_price > 0:
        position_size = int(position_value / entry_price)
    else:
        position_size = 0

    actual_position_value = position_size * entry_price

    risk_per_share = 0
    if stop_loss is not None and entry_price > stop_loss:
        risk_per_share = entry_price - stop_loss

    total_risk = risk_per_share * position_size
    risk_pct = (total_risk / capital) * 100 if capital > 0 else 0

    return {
        "capital": capital,
        "kelly_fraction": kelly_fraction,
        "position_value": position_value,
        "max_position_value": max_position_value,
        "position_size": position_size,
        "actual_position_value": actual_position_value,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "risk_per_share": risk_per_share,
        "total_risk": total_risk,
        "risk_pct": risk_pct,
    }


def calculate_kelly_from_history(
    trade_history: list[dict],
) -> KellyResult:
    """Hitung Kelly Criterion dari trade history.

    Args:
        trade_history: List of trade dicts dengan keys: pnl (decimal return).

    Returns:
        KellyResult.
    """
    if not trade_history:
        raise ValueError("Trade history cannot be empty")

    winning_trades = [t["pnl"] for t in trade_history if t["pnl"] > 0]
    losing_trades = [abs(t["pnl"]) for t in trade_history if t["pnl"] < 0]

    if not winning_trades or not losing_trades:
        raise ValueError("Trade history must have both winning and losing trades")

    win_rate = len(winning_trades) / len(trade_history)
    avg_win = float(np.mean(winning_trades))
    avg_loss = float(np.mean(losing_trades))

    return calculate_kelly_criterion(win_rate, avg_win, avg_loss)
