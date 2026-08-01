"""Liquidity Filter — adopted from ML app, adapted for trading-system.

Filters illiquid stocks based on average daily volume.
Integrates with analysis/screener.py and analysis/factor_screener.py.
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


class LiquidityFilter:
    """Filter illiquid stocks for IDX market."""

    def __init__(self, min_volume: int = 100_000, min_trading_days: int = 20) -> None:
        self.min_volume = min_volume
        self.min_trading_days = min_trading_days

    def is_liquid(self, data: pd.DataFrame, window: int = 20) -> bool:
        """Check if a stock is liquid based on average volume.

        Args:
            data: DataFrame with 'volume' column.
            window: Rolling window for average volume calculation.

        Returns:
            True if stock meets liquidity criteria.
        """
        if data.empty or "volume" not in data.columns:
            return False

        if len(data) < self.min_trading_days:
            return False

        avg_volume = data["volume"].rolling(window=window).mean().iloc[-1]
        if pd.isna(avg_volume):
            avg_volume = data["volume"].mean()

        return bool(avg_volume >= self.min_volume)

    def filter_liquid(
        self, tickers_data: dict[str, pd.DataFrame], window: int = 20
    ) -> dict[str, pd.DataFrame]:
        """Filter a dictionary of ticker → DataFrame, keeping only liquid stocks.

        Args:
            tickers_data: Dict mapping ticker to OHLCV DataFrame.
            window: Rolling window for volume calculation.

        Returns:
            Filtered dict with only liquid tickers.
        """
        liquid = {}
        for ticker, df in tickers_data.items():
            if self.is_liquid(df, window):
                liquid[ticker] = df
            else:
                logger.debug("Filtered illiquid: %s", ticker)
        return liquid

    def get_liquidity_score(self, data: pd.DataFrame, window: int = 20) -> float:
        """Return a liquidity score 0-100 based on volume consistency.

        Higher score = more liquid.
        """
        if data.empty or "volume" not in data.columns or len(data) < window:
            return 0.0

        avg_vol = data["volume"].rolling(window=window).mean().iloc[-1]
        if pd.isna(avg_vol) or avg_vol == 0:
            return 0.0

        vol_ratio = avg_vol / self.min_volume
        score = min(vol_ratio * 50, 100.0)

        vol_std = data["volume"].rolling(window=window).std().iloc[-1]
        if not pd.isna(vol_std) and avg_vol > 0:
            cv = vol_std / avg_vol
            consistency = max(0, 1 - cv)
            score = score * 0.7 + consistency * 30

        return round(score, 2)
