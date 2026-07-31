"""Consolidated ATR, fee, and slippage calculations (P2-4, §4.5).

Single source of truth for:
- ATR (Average True Range) computation
- Transaction cost model (broker fee, levy, tax, slippage)
- Slippage estimation based on order size vs daily volume

Used by: risk/engine.py, execution/engine.py, execution/automated.py,
backtest/engine.py, analysis/technical.py, risk/enhanced_risk.py
"""

from __future__ import annotations

import pandas as pd

from trading_system.config import (
    DEFAULT_BROKER_FEE_BUY,
    DEFAULT_BROKER_FEE_SELL,
    DEFAULT_LEVY,
    DEFAULT_SLIPPAGE,
)


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute Average True Range (ATR) for a DataFrame.

    Uses True Range = max(high-low, |high-prev_close|, |low-prev_close|).
    Returns a Series (not scalar) so callers can pick the latest or any bar.

    Args:
        df: OHLCV DataFrame with 'high', 'low', 'close' columns.
        period: ATR period (default 14).

    Returns:
        Series of ATR values (NaN for first `period-1` bars).
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def get_latest_atr(df: pd.DataFrame, period: int = 14) -> float:
    """Get the latest ATR value as a scalar.

    Returns 0.0 if insufficient data.
    """
    if df is None or df.empty or len(df) < period:
        return 0.0
    atr_series = compute_atr(df, period)
    val = atr_series.iloc[-1]
    return float(val) if not pd.isna(val) else 0.0


class CostModel:
    """Consolidated transaction cost model for IDX.

    Single source of truth for broker fees, levy, tax, and slippage.
    All fee rates are in decimal (e.g., 0.0015 = 0.15%).

    Attributes:
        buy_fee: Broker fee for buy (default 0.15%).
        sell_fee: Broker fee + PPh for sell (default 0.25%).
        levy: Exchange levy (default 0.00043%).
        slippage: Default slippage rate (default 0.05%).
    """

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

    def buy_cost_pct(self) -> float:
        """Total cost percentage for buy (fee + levy + slippage)."""
        return self.buy_fee + self.levy + self.slippage

    def sell_cost_pct(self) -> float:
        """Total cost percentage for sell (fee + levy + slippage)."""
        return self.sell_fee + self.levy + self.slippage

    def compute_fees(self, order_value: float, action: str = "buy") -> dict:
        """Compute fee breakdown for an order.

        Args:
            order_value: Gross order value in IDR.
            action: "buy" or "sell".

        Returns:
            Dict with brokerage, levy, tax, total.
        """
        fee_rate = self.buy_fee if action == "buy" else self.sell_fee
        brokerage = order_value * fee_rate
        levy = order_value * self.levy
        tax = order_value * (0.001 if action == "sell" else 0)  # PPh 0.1% sell only
        return {
            "brokerage": round(brokerage, 2),
            "levy": round(levy, 2),
            "tax": round(tax, 2),
            "total": round(brokerage + levy + tax, 2),
        }

    def estimate_slippage(self, order_value: float, avg_daily_value: float) -> float:
        """Estimate slippage based on order size vs daily volume.

        Args:
            order_value: Gross order value in IDR.
            avg_daily_value: Average daily traded value in IDR.

        Returns:
            Slippage as decimal (e.g., 0.0005 = 0.05%).
        """
        if avg_daily_value <= 0:
            return self.slippage
        ratio = order_value / avg_daily_value
        if ratio < 0.001:
            return self.slippage
        if ratio < 0.01:
            return self.slippage * 2
        return self.slippage * 4

    def simulate_fill(
        self,
        action: str,
        shares: int,
        last_price: float,
        avg_daily_value: float = 0,
    ) -> dict:
        """Simulate order fill with slippage and fees.

        Args:
            action: "buy" or "sell".
            shares: Number of shares.
            last_price: Last market price.
            avg_daily_value: Average daily traded value for slippage estimation.

        Returns:
            Dict with fill_price, gross_value, fees, net_value, slippage_pct.
        """
        action = action.lower()
        order_value = shares * last_price
        slip = self.estimate_slippage(order_value, avg_daily_value)
        fill_price = last_price * (1 + slip) if action == "buy" else last_price * (1 - slip)
        fees = self.compute_fees(order_value, action)
        net = order_value + fees["total"] if action == "buy" else order_value - fees["total"]
        return {
            "action": action.upper(),
            "shares": shares,
            "fill_price": round(fill_price, 2),
            "gross_value": round(order_value, 2),
            "fees": fees,
            "net_value": round(net, 2),
            "slippage_pct": round(slip * 100, 4),
        }

    def check_feasibility(
        self,
        shares: int,
        price: float,
        cash: float,
        avg_daily_value: float = 0,
    ) -> dict:
        """Check if a buy order is feasible given available cash.

        Args:
            shares: Number of shares to buy.
            price: Target price.
            cash: Available cash.
            avg_daily_value: For slippage estimation.

        Returns:
            Dict with feasible, required_cash, available_cash, slippage_pct.
        """
        order_value = shares * price
        slip = self.estimate_slippage(order_value, avg_daily_value)
        total_cost = order_value * (1 + self.buy_fee + self.levy + slip)
        return {
            "feasible": cash >= total_cost,
            "required_cash": round(total_cost, 2),
            "available_cash": round(cash, 2),
            "slippage_pct": round(slip * 100, 4),
        }


# Singleton instance for convenience
_default_cost_model = CostModel()


def get_default_cost_model() -> CostModel:
    """Get the default shared CostModel instance."""
    return _default_cost_model
