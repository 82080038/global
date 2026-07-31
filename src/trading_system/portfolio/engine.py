"""Portfolio Engine — mengelola alokasi modal berdasarkan rekomendasi dan posisi aktif.

Membaca posisi dari tabel positions, generate orders BUY/SELL berdasarkan
rekomendasi Decision Engine, dan track exposure per ticker.
"""

from __future__ import annotations

import logging

import pandas as pd

from trading_system.data.storage import DataStorage

logger = logging.getLogger(__name__)


class PortfolioEngine:
    name = "portfolio"

    def __init__(self, storage: DataStorage | None = None, cash: float = 1_000_000_000):
        self.storage = storage or DataStorage()
        self.cash = cash

    def current_positions(self) -> pd.DataFrame:
        """Load all open positions from database."""
        positions = self.storage.get_all_open_positions()
        if not positions:
            return pd.DataFrame([{"ticker": "CASH", "quantity": self.cash, "avg_price": 1.0}])
        df = pd.DataFrame(positions)
        df = df[["ticker", "quantity", "avg_entry_price"]].rename(columns={"avg_entry_price": "avg_price"})
        return df

    def get_exposure(self) -> dict:
        """Calculate current portfolio exposure."""
        positions = self.storage.get_all_open_positions()
        total_invested = sum(float(p.get("quantity", 0)) * float(p.get("avg_entry_price", 0)) for p in positions)
        total_equity = self.cash + total_invested
        exposure_pct = (total_invested / total_equity * 100) if total_equity > 0 else 0
        return {
            "cash": self.cash,
            "invested": total_invested,
            "total_equity": total_equity,
            "exposure_pct": round(exposure_pct, 2),
            "position_count": len(positions),
        }

    def generate_orders(self, recommendation: dict) -> list[dict]:
        """Generate orders from a recommendation.

        Handles both BUY (open new position) and SELL (close existing position).
        """
        action = recommendation.get("action")
        ticker = recommendation["ticker"]

        if action == "BUY":
            return self._generate_buy_order(ticker, recommendation)
        elif action == "SELL":
            return self._generate_sell_order(ticker, recommendation)
        return []

    def _generate_buy_order(self, ticker: str, recommendation: dict) -> list[dict]:
        """Generate a BUY order for a new position."""
        existing = self.storage.get_open_position(ticker)
        if existing:
            logger.info(f"Already have open position for {ticker}, skipping BUY")
            return []

        pos_size = recommendation.get("position_size", 0)
        capital_alloc = self.cash * pos_size
        entry = recommendation.get("entry_price_range", [0, 0])

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

    def _generate_sell_order(self, ticker: str, recommendation: dict) -> list[dict]:
        """Generate a SELL order to close an existing position."""
        position = self.storage.get_open_position(ticker)
        if not position:
            return []

        qty = int(position.get("quantity", 0))
        if qty <= 0:
            return []

        entry = recommendation.get("entry_price_range", [0, 0])
        try:
            mid_price = (float(entry[0]) + float(entry[1])) / 2
        except Exception:
            mid_price = 0

        if mid_price <= 0:
            df = self.storage.load_ohlcv(ticker)
            if df.empty:
                return []
            mid_price = float(df["close"].iloc[-1])

        return [{
            "ticker": ticker,
            "action": "SELL",
            "shares": qty,
            "target_price": mid_price,
            "order_value": qty * mid_price,
        }]
