"""Profit Tracker — adaptasi dari pustaka/16-strategi-mencari-keuntungan.md.

Track dan analisis sumber keuntungan portofolio:
- Capital gain (appreciation)
- Dividend income
- Total return
- ROI
- Yield on cost

Memecah return berdasarkan sumber untuk evaluasi strategi.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Position:
    """Single portfolio position."""
    ticker: str
    shares: int
    avg_cost: float
    dividends_received: float = 0.0
    sector: str = "unknown"


@dataclass
class ProfitBreakdown:
    """Profit breakdown for a single position."""
    ticker: str
    shares: int
    cost_basis: float
    current_value: float
    capital_gain: float
    capital_gain_pct: float
    dividends: float
    dividend_yield_pct: float
    total_return: float
    total_return_pct: float

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "shares": self.shares,
            "cost_basis": round(self.cost_basis, 2),
            "current_value": round(self.current_value, 2),
            "capital_gain": round(self.capital_gain, 2),
            "capital_gain_pct": round(self.capital_gain_pct, 4),
            "dividends": round(self.dividends, 2),
            "dividend_yield_pct": round(self.dividend_yield_pct, 4),
            "total_return": round(self.total_return, 2),
            "total_return_pct": round(self.total_return_pct, 4),
        }


@dataclass
class PortfolioProfitReport:
    """Aggregate profit report for entire portfolio."""
    total_cost: float = 0.0
    total_value: float = 0.0
    total_capital_gain: float = 0.0
    total_dividends: float = 0.0
    total_return: float = 0.0
    roi: float = 0.0
    capital_gain_pct: float = 0.0
    dividend_yield_pct: float = 0.0
    positions: list[ProfitBreakdown] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_cost": round(self.total_cost, 2),
            "total_value": round(self.total_value, 2),
            "total_capital_gain": round(self.total_capital_gain, 2),
            "total_dividends": round(self.total_dividends, 2),
            "total_return": round(self.total_return, 2),
            "roi": round(self.roi, 4),
            "capital_gain_pct": round(self.capital_gain_pct, 4),
            "dividend_yield_pct": round(self.dividend_yield_pct, 4),
            "positions": [p.to_dict() for p in self.positions],
        }


def calculate_position_profit(
    position: Position,
    current_price: float,
) -> ProfitBreakdown:
    """Calculate profit breakdown for a single position.

    Args:
        position: Position with shares, avg_cost, dividends_received.
        current_price: Current market price per share.

    Returns:
        ProfitBreakdown with capital gain, dividend, and total return.
    """
    cost_basis = position.shares * position.avg_cost
    current_value = position.shares * current_price
    capital_gain = current_value - cost_basis
    capital_gain_pct = capital_gain / cost_basis if cost_basis > 0 else 0.0
    dividend_yield_pct = position.dividends_received / cost_basis if cost_basis > 0 else 0.0
    total_return = capital_gain + position.dividends_received
    total_return_pct = total_return / cost_basis if cost_basis > 0 else 0.0

    return ProfitBreakdown(
        ticker=position.ticker,
        shares=position.shares,
        cost_basis=cost_basis,
        current_value=current_value,
        capital_gain=capital_gain,
        capital_gain_pct=capital_gain_pct,
        dividends=position.dividends_received,
        dividend_yield_pct=dividend_yield_pct,
        total_return=total_return,
        total_return_pct=total_return_pct,
    )


def calculate_portfolio_profit(
    positions: list[Position],
    current_prices: dict[str, float],
) -> PortfolioProfitReport:
    """Calculate aggregate profit breakdown for entire portfolio.

    Args:
        positions: List of Position objects.
        current_prices: Dict mapping ticker to current price.

    Returns:
        PortfolioProfitReport with aggregate and per-position breakdowns.
    """
    breakdowns: list[ProfitBreakdown] = []
    total_cost = 0.0
    total_value = 0.0
    total_capital_gain = 0.0
    total_dividends = 0.0

    for pos in positions:
        price = current_prices.get(pos.ticker, 0.0)
        breakdown = calculate_position_profit(pos, price)
        breakdowns.append(breakdown)

        total_cost += breakdown.cost_basis
        total_value += breakdown.current_value
        total_capital_gain += breakdown.capital_gain
        total_dividends += breakdown.dividends

    total_return = total_capital_gain + total_dividends
    roi = total_return / total_cost if total_cost > 0 else 0.0
    capital_gain_pct = total_capital_gain / total_cost if total_cost > 0 else 0.0
    dividend_yield_pct = total_dividends / total_cost if total_cost > 0 else 0.0

    return PortfolioProfitReport(
        total_cost=total_cost,
        total_value=total_value,
        total_capital_gain=total_capital_gain,
        total_dividends=total_dividends,
        total_return=total_return,
        roi=roi,
        capital_gain_pct=capital_gain_pct,
        dividend_yield_pct=dividend_yield_pct,
        positions=breakdowns,
    )


def calculate_expectancy(
    trades: list[float],
    min_sample: int = 10,
) -> dict:
    """Calculate expectancy from a list of R-multiples.

    Args:
        trades: List of R-multiples (positive = win, negative = loss).
        min_sample: Minimum number of trades for meaningful stats.

    Returns:
        Dict with win_rate, avg_win, avg_loss, expectancy.
    """
    if len(trades) < min_sample:
        return {
            "available": False,
            "message": f"Need at least {min_sample} trades, got {len(trades)}",
        }

    wins = [r for r in trades if r > 0]
    losses = [r for r in trades if r < 0]

    win_rate = len(wins) / len(trades) if trades else 0
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

    return {
        "available": True,
        "n_trades": len(trades),
        "win_rate": round(win_rate, 4),
        "avg_win": round(avg_win, 4),
        "avg_loss": round(avg_loss, 4),
        "expectancy": round(expectancy, 4),
        "profitable": expectancy > 0,
    }
