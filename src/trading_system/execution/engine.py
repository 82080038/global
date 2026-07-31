"""Execution Engine (Fase 4) — minimal.

Menghitung biaya transaksi realistis dan memeriksa ke layakan order.
Uses consolidated CostModel from risk/costs.py (P2-4).
"""

from __future__ import annotations

from trading_system.risk.costs import CostModel, get_default_cost_model


class ExecutionEngine:
    name = "execution"

    def __init__(self, cost_model: CostModel | None = None):
        self.cost_model = cost_model or get_default_cost_model()

    def compute_fees(self, order_value: float, action: str = "buy") -> dict:
        return self.cost_model.compute_fees(order_value, action)

    def estimate_slippage(self, order_value: float, avg_daily_value: float) -> float:
        return self.cost_model.estimate_slippage(order_value, avg_daily_value)

    def simulate_fill(self, order: dict, last_price: float, avg_daily_value: float) -> dict:
        action = order.get("action", "buy").lower()
        shares = order.get("shares", 0)
        result = self.cost_model.simulate_fill(action, shares, last_price, avg_daily_value)
        result["ticker"] = order["ticker"]
        return result

    def check_feasibility(self, order: dict, cash: float, avg_daily_value: float) -> dict:
        shares = order.get("shares", 0)
        price = order.get("target_price", 0)
        result = self.cost_model.check_feasibility(shares, price, cash, avg_daily_value)
        return result
