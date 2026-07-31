"""Performance Analytics Engine — Equity Curve, Sharpe, Drawdown, Win Rate.

Menghitung metrik kinerja portofolio dari order history dan equity snapshots.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

from trading_system.data.storage import DataStorage

logger = logging.getLogger(__name__)


class PerformanceAnalytics:
    """Compute portfolio performance metrics from orders and equity snapshots."""

    name = "performance_analytics"

    def __init__(self, storage: DataStorage | None = None):
        self.storage = storage or DataStorage()
        self.initial_capital = float(
            __import__("os").getenv("TRADING_CAPITAL", "100000000")
        )

    def _get_latest_price(self, ticker: str) -> float | None:
        """Get latest close price from OHLCV data."""
        df = self.storage.load_ohlcv(ticker)
        if df.empty:
            return None
        return float(df["close"].iloc[-1])

    def compute_equity(self) -> float:
        """Compute current total equity = cash + positions market value."""
        positions = self.storage.get_all_open_positions()
        positions_value = 0.0
        for pos in positions:
            price = self._get_latest_price(pos["ticker"])
            if price:
                positions_value += price * pos["quantity"]

        # Cash = initial_capital - total buy value + total sell value
        orders = self.storage.get_orders(limit=10000)
        total_bought = sum(
            float(o["total_value"]) + float(o.get("fee", 0))
            for o in orders if o.get("order_type") == "BUY"
        )
        total_sold = sum(
            float(o["total_value"]) - float(o.get("fee", 0))
            for o in orders if o.get("order_type") == "SELL"
        )
        cash = self.initial_capital - total_bought + total_sold
        return cash + positions_value

    def save_daily_snapshot(self):
        """Save today's equity snapshot to DB for historical tracking."""
        positions = self.storage.get_all_open_positions()
        positions_value = 0.0
        unrealized_pnl = 0.0
        for pos in positions:
            price = self._get_latest_price(pos["ticker"])
            if price:
                positions_value += price * pos["quantity"]
                entry = pos.get("avg_entry_price", 0)
                unrealized_pnl += (price - entry) * pos["quantity"]

        orders = self.storage.get_orders(limit=10000)
        total_bought = sum(
            float(o["total_value"]) + float(o.get("fee", 0))
            for o in orders if o.get("order_type") == "BUY"
        )
        total_sold = sum(
            float(o["total_value"]) - float(o.get("fee", 0))
            for o in orders if o.get("order_type") == "SELL"
        )
        cash = self.initial_capital - total_bought + total_sold
        equity = cash + positions_value

        realized_pnl = sum(
            float(o.get("total_value", 0)) - float(o.get("fee", 0))
            for o in orders if o.get("order_type") == "SELL"
        ) - sum(
            float(o.get("total_value", 0)) + float(o.get("fee", 0))
            for o in orders if o.get("order_type") == "BUY"
        ) + positions_value

        total_return_pct = ((equity - self.initial_capital) / self.initial_capital) * 100

        self.storage.save_equity_snapshot(
            equity=equity, cash=cash, positions_value=positions_value,
            realized_pnl=realized_pnl, unrealized_pnl=unrealized_pnl,
            total_return_pct=total_return_pct,
        )
        logger.info(f"Equity snapshot saved: Rp {equity:,.0f} (return: {total_return_pct:.2f}%)")
        return equity

    def get_performance(self, period: str = "1M") -> dict[str, Any]:
        """Compute performance metrics for the given period.

        Args:
            period: 1W, 1M, 3M, 6M, 1Y, ALL

        Returns:
            Dict with total_return, sharpe_ratio, max_drawdown, win_rate,
            total_trades, current_equity, equity_curve
        """
        # Get equity snapshots from DB
        snapshots = self.storage.get_equity_snapshots(limit=365)

        # Filter by period
        period_days = {
            "1W": 7, "1M": 30, "3M": 90, "6M": 180, "1Y": 365, "ALL": 99999
        }
        days = period_days.get(period, 30)

        if snapshots:
            # Filter snapshots by date range
            cutoff = datetime.now(timezone.utc).date()
            from datetime import timedelta
            cutoff = cutoff - timedelta(days=days)
            filtered = [
                s for s in snapshots
                if s.get("date", "") >= cutoff.isoformat()
            ]
            if not filtered:
                filtered = snapshots[-days:] if len(snapshots) > days else snapshots

            equity_curve = [
                {"date": s["date"], "equity": s["equity"]}
                for s in filtered
            ]
            current_equity = filtered[-1]["equity"] if filtered else self.initial_capital
            start_equity = filtered[0]["equity"] if filtered else self.initial_capital
        else:
            # No snapshots, compute from orders
            current_equity = self.compute_equity()
            start_equity = self.initial_capital
            equity_curve = [{"date": datetime.now(timezone.utc).date().isoformat(),
                              "equity": current_equity}]

        # Total return
        total_return = ((current_equity - start_equity) / start_equity) * 100 if start_equity > 0 else 0

        # Sharpe ratio from equity curve
        sharpe = 0.0
        if len(equity_curve) > 1:
            returns = []
            for i in range(1, len(equity_curve)):
                prev = equity_curve[i - 1]["equity"]
                curr = equity_curve[i]["equity"]
                if prev > 0:
                    returns.append((curr / prev) - 1)
            if returns:
                avg_return = sum(returns) / len(returns)
                std_return = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5
                if std_return > 0:
                    sharpe = (avg_return / std_return) * math.sqrt(252)

        # Max drawdown
        max_equity = start_equity
        max_drawdown = 0.0
        for point in equity_curve:
            eq = point["equity"]
            if eq > max_equity:
                max_equity = eq
            dd = ((max_equity - eq) / max_equity) * 100 if max_equity > 0 else 0
            if dd > max_drawdown:
                max_drawdown = dd

        # Win rate from orders
        orders = self.storage.get_orders(limit=10000)
        sell_orders = [o for o in orders if o.get("order_type") == "SELL"]
        buy_orders = [o for o in orders if o.get("order_type") == "BUY"]

        wins = 0
        total_sells = len(sell_orders)
        for sell in sell_orders:
            ticker = sell.get("ticker", "")
            ticker_buys = [o for o in buy_orders if o.get("ticker") == ticker]
            if ticker_buys:
                avg_buy = sum(float(o["price"]) for o in ticker_buys) / len(ticker_buys)
                if float(sell["price"]) > avg_buy:
                    wins += 1

        win_rate = (wins / total_sells * 100) if total_sells > 0 else 0

        return {
            "total_return": round(total_return, 2),
            "sharpe_ratio": round(sharpe, 2),
            "max_drawdown": round(max_drawdown, 2),
            "win_rate": round(win_rate, 2),
            "total_trades": len(orders),
            "current_equity": round(current_equity, 2),
            "initial_capital": self.initial_capital,
            "equity_curve": equity_curve[-90:],  # Last 90 data points
        }
