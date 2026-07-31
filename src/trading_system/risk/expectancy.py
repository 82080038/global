"""Trading Expectancy Calculator (V, §4.1).

Computes win rate, risk-reward ratio, expectancy, and Kelly criterion
for position sizing based on historical trade results.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class TradeResult:
    """Result of a single trade."""
    symbol: str
    entry_price: float
    exit_price: float
    shares: int
    side: str = "long"  # "long" or "short"


class TradingExpectancy:
    """Calculate trading performance metrics from trade history."""

    @staticmethod
    def compute(trades: list[TradeResult]) -> dict[str, float]:
        """Compute expectancy metrics from a list of trades.

        Returns dict with: win_rate, avg_win, avg_loss, rrr, expectancy, kelly_fraction.
        """
        if not trades:
            return {
                "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
                "rrr": 0.0, "expectancy": 0.0, "kelly_fraction": 0.0,
                "total_trades": 0, "total_pnl": 0.0,
            }

        pnls = []
        for t in trades:
            if t.side == "long":
                pnl = (t.exit_price - t.entry_price) * t.shares
            else:
                pnl = (t.entry_price - t.exit_price) * t.shares
            pnls.append(pnl)

        pnls = np.array(pnls)
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]

        win_rate = len(wins) / len(pnls) if len(pnls) > 0 else 0.0
        avg_win = float(np.mean(wins)) if len(wins) > 0 else 0.0
        avg_loss = float(np.mean(losses)) if len(losses) > 0 else 0.0
        rrr = abs(avg_win / avg_loss) if avg_loss != 0 else 0.0
        expectancy = float(np.mean(pnls))
        total_pnl = float(np.sum(pnls))

        # Kelly criterion: f = (bp - q) / b
        # where b = win/loss ratio, p = win rate, q = 1 - p
        if avg_loss != 0 and win_rate > 0:
            b = abs(avg_win / avg_loss)
            p = win_rate
            q = 1 - p
            kelly = (b * p - q) / b if b > 0 else 0.0
        else:
            kelly = 0.0

        return {
            "win_rate": round(win_rate, 4),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "rrr": round(rrr, 4),
            "expectancy": round(expectancy, 2),
            "kelly_fraction": round(max(0.0, kelly), 4),
            "total_trades": len(trades),
            "total_pnl": round(total_pnl, 2),
        }
