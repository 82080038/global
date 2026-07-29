"""Technical Analysis Engine (Fase 2)."""

from __future__ import annotations

import numpy as np
import pandas as pd


class TechnicalAnalysisEngine:
    """Menganalisis perilaku harga & volume, menghasilkan technical_score (0-100)."""

    name = "technical"

    def __init__(self, ohlcv: pd.DataFrame | None = None):
        self.ohlcv = ohlcv

    def load_ohlcv(self, storage, ticker: str, **kwargs) -> pd.DataFrame:
        self.ohlcv = storage.load_ohlcv(ticker, **kwargs)
        return self.ohlcv

    def compute_indicators(self) -> pd.DataFrame:
        df = self.ohlcv.copy()
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        # Moving averages
        df["ma_20"] = close.rolling(20).mean()
        df["ma_50"] = close.rolling(50).mean()

        # ADX sederhana
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr_14 = tr.rolling(14).mean()
        plus_di = 100 * plus_dm.rolling(14).mean() / atr_14
        minus_di = 100 * minus_dm.rolling(14).mean() / atr_14
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        df["adx"] = dx.rolling(14).mean()

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss
        df["rsi"] = 100 - (100 / (1 + rs))

        # MACD
        ema_12 = close.ewm(span=12).mean()
        ema_26 = close.ewm(span=26).mean()
        df["macd"] = ema_12 - ema_26
        df["macd_signal"] = df["macd"].ewm(span=9).mean()

        # ATR / Bollinger
        df["atr_14"] = atr_14
        df["bb_mid"] = close.rolling(20).mean()
        df["bb_std"] = close.rolling(20).std()
        df["bb_upper"] = df["bb_mid"] + 2 * df["bb_std"]
        df["bb_lower"] = df["bb_mid"] - 2 * df["bb_std"]

        # Volume
        df["volume_sma_20"] = volume.rolling(20).mean()
        df["volume_ratio"] = volume / df["volume_sma_20"]

        # Volatility regime
        df["volatility_20"] = close.pct_change().rolling(20).std() * np.sqrt(252)

        return df

    def classify_trend_regime(self, df: pd.DataFrame) -> str:
        last = df.iloc[-1]
        if pd.isna(last["ma_20"]) or pd.isna(last["ma_50"]):
            return "unknown"
        if last["ma_20"] > last["ma_50"] and last["close"] > last["ma_20"]:
            return "uptrend"
        if last["ma_20"] < last["ma_50"] and last["close"] < last["ma_20"]:
            return "downtrend"
        return "sideways"

    def volume_profile(self, df: pd.DataFrame, n_bins: int = 10) -> dict:
        """Sederhana: distribusi volume berdasarkan harga close."""
        close = df["close"].dropna()
        volume = df["volume"].dropna()
        if len(close) < n_bins:
            return {"poc": None, "vah": None, "val": None}

        hist, edges = np.histogram(close, bins=n_bins, weights=volume)
        poc_idx = int(np.argmax(hist))
        poc = (edges[poc_idx] + edges[poc_idx + 1]) / 2
        cumvol = np.cumsum(hist) / hist.sum()
        vah_idx = int(np.searchsorted(cumvol, 0.70))
        val_idx = int(np.searchsorted(cumvol, 0.30))
        vah = (edges[vah_idx] + edges[vah_idx + 1]) / 2
        val = (edges[val_idx] + edges[val_idx + 1]) / 2
        return {"poc": round(poc, 4), "vah": round(vah, 4), "val": round(val, 4)}

    def compute_score(self, df: pd.DataFrame) -> tuple[float, dict]:
        last = df.iloc[-1]
        breakdown = {}

        # Trend score (0-25)
        trend = self.classify_trend_regime(df)
        if trend == "uptrend":
            breakdown["trend"] = 25
        elif trend == "downtrend":
            breakdown["trend"] = 0
        else:
            breakdown["trend"] = 12

        # Momentum score (0-25): RSI dan MACD
        rsi = last.get("rsi", 50)
        if pd.isna(rsi):
            rsi = 50
        breakdown["rsi"] = min(max((rsi - 30) * (25 / 40), 0), 25)  # 30->0, 70->25

        macd = last.get("macd", 0)
        macd_signal = last.get("macd_signal", 0)
        if pd.isna(macd) or pd.isna(macd_signal):
            breakdown["macd"] = 12
        else:
            breakdown["macd"] = 25 if macd > macd_signal else 0

        # Volatility score (0-25): penalize for very high volatility, reward low
        vol = last.get("volatility_20", 0.2)
        if pd.isna(vol):
            vol = 0.2
        breakdown["volatility"] = max(0, 25 - int(vol * 100))

        # Volume score (0-25): recent volume above average is good in uptrend
        vol_ratio = last.get("volume_ratio", 1.0)
        if pd.isna(vol_ratio):
            vol_ratio = 1.0
        breakdown["volume"] = min(25, int(vol_ratio * 12.5))

        score = sum(breakdown.values())
        return float(score), breakdown

    def analyze(self) -> dict:
        if self.ohlcv is None or self.ohlcv.empty:
            return {"status": "error", "message": "No OHLCV data"}
        df = self.compute_indicators()
        regime = self.classify_trend_regime(df)
        vp = self.volume_profile(df)
        score, breakdown = self.compute_score(df)
        return {
            "status": "ok",
            "engine": self.name,
            "score": round(score, 2),
            "regime": regime,
            "volume_profile": vp,
            "breakdown": breakdown,
        }
