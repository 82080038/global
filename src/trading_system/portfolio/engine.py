"""Portfolio Engine (Fase 4) — minimal.

Mengelola alokasi modal sederhana berdasarkan rekomendasi BUY/HOLD/SELL.
"""

from __future__ import annotations

import pandas as pd

from trading_system.data.storage import DataStorage


class PortfolioEngine:
    name = "portfolio"

    def __init__(self, storage: DataStorage | None = None, cash: float = 1_000_000_000):
        self.storage = storage or DataStorage()
        self.cash = cash

    def current_positions(self) -> pd.DataFrame:
        """Sementara hardcoded cash only; nanti ambil dari tabel positions."""
        return pd.DataFrame([{"ticker": "CASH", "quantity": self.cash, "avg_price": 1.0}])

    def generate_orders(self, recommendation: dict) -> list[dict]:
        if recommendation.get("action") != "BUY":
            return []

        ticker = recommendation["ticker"]
        pos_size = recommendation.get("position_size", 0)
        capital_alloc = self.cash * pos_size
        entry = recommendation.get("entry_price_range", [0, 0])

        # Avoid division by zero if entry range not available
        try:
            mid_price = (float(entry[0]) + float(entry[1])) / 2
        except Exception:
            mid_price = 0

        if mid_price <= 0:
            return []

        shares = int(capital_alloc // mid_price)
        if shares <= 0:
            return []

        return [{
            "ticker": ticker,
            "action": "BUY",
            "shares": shares,
            "target_price": mid_price,
            "order_value": shares * mid_price,
        }]
