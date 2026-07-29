"""Paper Trading Module (Fase 5).

Mensimulasikan order dari rekomendasi dengan harga pasar saat ini,
menghitung fill price, biaya, dan PnL awal.
"""

from __future__ import annotations

from datetime import datetime, timezone

from trading_system.data.storage import DataStorage
from trading_system.decision.engine import DecisionEngine
from trading_system.portfolio.engine import PortfolioEngine
from trading_system.execution.engine import ExecutionEngine


class PaperTradingEngine:
    name = "paper_trading"

    def __init__(self, storage: DataStorage | None = None, cash: float = 1_000_000_000):
        self.storage = storage or DataStorage()
        self.cash = cash
        self.portfolio = PortfolioEngine(storage, cash)
        self.execution = ExecutionEngine()

    def simulate(self, ticker: str) -> dict:
        decision = DecisionEngine(self.storage).recommend(ticker)
        if decision["status"] == "error":
            return decision

        rec = decision["recommendation"]
        orders = self.portfolio.generate_orders(rec)
        if not orders:
            return {
                "status": "ok",
                "ticker": ticker,
                "action": rec["action"],
                "message": "No paper trade generated (action not BUY or insufficient data).",
            }

        order = orders[0]
        df = self.storage.load_ohlcv(ticker)
        last_price = float(df["close"].iloc[-1]) if not df.empty else order["target_price"]
        avg_daily_value = df["volume"].tail(20).mean() * last_price if not df.empty else 0

        feasible = self.execution.check_feasibility(order, self.cash, avg_daily_value)
        fill = self.execution.simulate_fill(order, last_price, avg_daily_value)

        return {
            "status": "ok",
            "ticker": ticker,
            "recommendation": rec,
            "order": order,
            "feasibility": feasible,
            "simulated_fill": fill,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
