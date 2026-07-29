"""Strategi benchmark untuk Phase 1."""

from __future__ import annotations

import pandas as pd


class BuyAndHold:
    """Beli di hari pertama, hold sampai akhir."""

    name = "buy_and_hold"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["signal"] = 0
        df.iloc[0, df.columns.get_loc("signal")] = 1
        df.iloc[-1, df.columns.get_loc("signal")] = -1
        return df


class MovingAverageCrossover:
    """MA sederhana: fast > slow -> BUY, fast < slow -> SELL."""

    def __init__(self, fast: int = 20, slow: int = 50):
        self.fast = fast
        self.slow = slow
        self.name = f"ma_crossover_{fast}_{slow}"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df[f"ma_{self.fast}"] = df["close"].rolling(self.fast).mean()
        df[f"ma_{self.slow}"] = df["close"].rolling(self.slow).mean()
        df["signal"] = 0
        fast_col = f"ma_{self.fast}"
        slow_col = f"ma_{self.slow}"
        buy = df[fast_col] > df[slow_col]
        sell = df[fast_col] < df[slow_col]
        # Hanya sinyal pada crossing
        df.loc[buy & (df[fast_col].shift(1) <= df[slow_col].shift(1)), "signal"] = 1
        df.loc[sell & (df[fast_col].shift(1) >= df[slow_col].shift(1)), "signal"] = -1
        return df
