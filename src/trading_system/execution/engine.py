"""Execution Engine (Fase 4) — minimal.

Menghitung biaya transaksi realistis dan memeriksa ke layakan order.
"""

from __future__ import annotations

from trading_system.config import (
    DEFAULT_BROKER_FEE_BUY,
    DEFAULT_BROKER_FEE_SELL,
    DEFAULT_LEVY,
    DEFAULT_SLIPPAGE,
)


class ExecutionEngine:
    name = "execution"

    def __init__(
        self,
        buy_fee: float = DEFAULT_BROKER_FEE_BUY,
        sell_fee: float = DEFAULT_BROKER_FEE_SELL,
        levy: float = DEFAULT_LEVY,
        slippage: float = DEFAULT_SLIPPAGE,
    ):
        self.buy_fee = buy_fee
        self.sell_fee = sell_fee
        self.levy = levy
        self.slippage = slippage

    def compute_fees(self, order_value: float, action: str = "buy") -> dict:
        fee = self.buy_fee if action == "buy" else self.sell_fee
        brokerage = order_value * fee
        levy = order_value * self.levy
        tax = order_value * (0.001 if action == "sell" else 0)
        return {
            "brokerage": round(brokerage, 2),
            "levy": round(levy, 2),
            "tax": round(tax, 2),
            "total": round(brokerage + levy + tax, 2),
        }

    def estimate_slippage(self, order_value: float, avg_daily_value: float) -> float:
        if avg_daily_value <= 0:
            return self.slippage
        ratio = order_value / avg_daily_value
        if ratio < 0.001:
            return self.slippage
        if ratio < 0.01:
            return self.slippage * 2
        return self.slippage * 4

    def simulate_fill(self, order: dict, last_price: float, avg_daily_value: float) -> dict:
        action = order.get("action", "buy").lower()
        shares = order.get("shares", 0)
        order_value = shares * last_price
        slippage = self.estimate_slippage(order_value, avg_daily_value)
        fill_price = last_price * (1 + slippage) if action == "buy" else last_price * (1 - slippage)
        fees = self.compute_fees(order_value, action)
        net = order_value + fees["total"] if action == "buy" else order_value - fees["total"]
        return {
            "ticker": order["ticker"],
            "action": action.upper(),
            "shares": shares,
            "fill_price": round(fill_price, 2),
            "gross_value": round(order_value, 2),
            "fees": fees,
            "net_value": round(net, 2),
            "slippage_pct": round(slippage * 100, 4),
        }

    def check_feasibility(self, order: dict, cash: float, avg_daily_value: float) -> dict:
        shares = order.get("shares", 0)
        price = order.get("target_price", 0)
        order_value = shares * price
        slippage = self.estimate_slippage(order_value, avg_daily_value)
        total_cost = order_value * (1 + self.buy_fee + self.levy + slippage)
        feasible = cash >= total_cost
        return {
            "feasible": feasible,
            "required_cash": round(total_cost, 2),
            "available_cash": round(cash, 2),
            "slippage_pct": round(slippage * 100, 4),
        }
