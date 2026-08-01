"""Slippage Model — adopted from ML app, adapted for trading-system.

Estimates slippage for IDX market based on order size, volume, and time of day.
Integrates with execution/engine.py and risk/costs.py.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class SlippageModel:
    """Slippage estimation for Indonesian stock market (IDX)."""

    def estimate_slippage(
        self,
        symbol: str,
        order_size: int,
        order_type: str = "MARKET",
        time_of_day: datetime | None = None,
        avg_daily_volume: int | None = None,
    ) -> float:
        """Estimate slippage as a fraction of price.

        Args:
            symbol: Stock ticker.
            order_size: Order size in shares.
            order_type: 'MARKET' or 'LIMIT'.
            time_of_day: Execution time (affects liquidity).
            avg_daily_volume: Average daily volume for volume impact calculation.

        Returns:
            Slippage as a fraction (e.g. 0.001 = 0.1%).
        """
        if order_type.upper() == "LIMIT":
            base_slippage = 0.0005
        else:
            base_slippage = 0.001

        volume_multiplier = 1.0
        if avg_daily_volume and avg_daily_volume > 0:
            volume_ratio = order_size / avg_daily_volume
            volume_multiplier = 1.0 + (volume_ratio * 10)

        time_multiplier = 1.0
        if time_of_day:
            hour = time_of_day.hour
            if hour == 13 and time_of_day.minute < 45:
                time_multiplier = 0.8
            elif hour >= 15:
                time_multiplier = 1.5
            elif hour < 10:
                time_multiplier = 1.2

        total_slippage = base_slippage * volume_multiplier * time_multiplier
        return min(total_slippage, 0.02)

    def estimate_slippage_cost(
        self,
        symbol: str,
        order_size: int,
        price: float,
        order_type: str = "MARKET",
        time_of_day: datetime | None = None,
        avg_daily_volume: int | None = None,
    ) -> dict[str, Any]:
        """Estimate slippage cost in rupiah.

        Returns dict with slippage_pct, slippage_cost_rp, and details.
        """
        slippage_pct = self.estimate_slippage(
            symbol, order_size, order_type, time_of_day, avg_daily_volume
        )
        order_value = order_size * price
        slippage_cost = order_value * slippage_pct

        return {
            "symbol": symbol,
            "order_size": order_size,
            "price": price,
            "order_value": order_value,
            "slippage_pct": slippage_pct,
            "slippage_cost_rp": slippage_cost,
            "order_type": order_type,
        }
