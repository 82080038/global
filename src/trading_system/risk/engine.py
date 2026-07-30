"""Risk Engine (Fase 4).

Menghitung ukuran posisi, stop loss, take profit, dan risk flags
berdasarkan volatilitas & likuiditas.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trading_system.data.storage import DataStorage


class RiskEngine:
    name = "risk"

    def __init__(self, storage: DataStorage | None = None):
        self.storage = storage or DataStorage()

    def analyze(self, ticker: str, capital: float = 1_000_000_000, risk_per_trade: float = 0.01) -> dict:
        df = self.storage.load_ohlcv(ticker)
        if df.empty:
            return {"status": "error", "message": f"No OHLCV for {ticker}"}

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        last_price = float(close.iloc[-1])
        atr = self._atr(df, 14)
        avg_volume_raw = float(volume.rolling(20).mean().iloc[-1]) if len(volume) >= 20 else float(volume.mean()) if not volume.empty else 0
        avg_volume = avg_volume_raw if not pd.isna(avg_volume_raw) else 0
        volatility_raw = float(close.pct_change().rolling(20).std().iloc[-1] * np.sqrt(252)) if len(close) >= 20 else 0.2
        volatility = volatility_raw if not pd.isna(volatility_raw) else 0.2

        # Position sizing: target risk 1% of capital, stop = 1.5 ATR
        stop_distance = 1.5 * atr if not pd.isna(atr) and atr > 0 else last_price * 0.05
        stop_loss = last_price - stop_distance
        take_profit = last_price + 2 * stop_distance

        # Fixed fraction position size
        risk_amount = capital * risk_per_trade
        position_value = risk_amount / (stop_distance / last_price)
        position_size = min(position_value / capital, 0.1)  # max 10% of capital

        # Liquidity: target position must be < 1% of avg daily volume value
        adv_value = avg_volume * last_price
        target_value = position_size * capital
        slippage = 0.0005  # 5 bps default
        if adv_value > 0 and target_value > adv_value * 0.01:
            slippage = 0.002  # 20 bps if too big
            flags = ["LIQUIDITY_LOW"]
        else:
            flags = []

        if volatility > 0.5:
            flags.append("HIGH_VOLATILITY")

        return {
            "status": "ok",
            "engine": self.name,
            "ticker": ticker,
            "last_price": round(last_price, 2),
            "atr": round(atr, 4) if not pd.isna(atr) else None,
            "position_size": round(position_size, 4),
            "stop_loss": round(stop_loss, 2),
            "take_profit": round(take_profit, 2),
            "slippage": round(slippage, 4),
            "risk_flags": flags,
            "avg_daily_volume": round(avg_volume, 0),
        }

    def _atr(self, df: pd.DataFrame, window: int = 14) -> float:
        high = df["high"]
        low = df["low"]
        close = df["close"]
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window).mean()
        return float(atr.iloc[-1]) if not atr.empty else np.nan
