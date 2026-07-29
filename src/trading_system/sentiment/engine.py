"""News & Sentiment Engine (Fase 3) — placeholder sederhana.

Belum terhubung ke sumber berita live. Menggunakan aturan sementara
berdasarkan perubahan harga & volume sebagai proxy sentimen.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trading_system.data.storage import DataStorage


class SentimentEngine:
    name = "sentiment"

    def __init__(self, storage: DataStorage | None = None):
        self.storage = storage or DataStorage()

    def compute(self, ticker: str) -> dict:
        df = self.storage.load_ohlcv(ticker)
        if df.empty:
            return {"status": "error", "message": "No OHLCV"}

        # Sentimen dari momentum harga & volume
        df["returns"] = df["close"].pct_change()
        df["vol_ma"] = df["volume"].rolling(20).mean()

        recent = df.iloc[-5:]
        avg_return = recent["returns"].mean()
        avg_volume = recent["volume"].mean()
        base_vol = df["volume"].tail(20).mean()
        vol_ratio = avg_volume / base_vol if base_vol > 0 else 1.0

        price_score = max(0, min(25, 12.5 + avg_return * 500))  # return positif -> score tinggi
        volume_score = min(25, vol_ratio * 12.5)
        # Konsolidasi kedua komponen menjadi sentimen (-1..1) dan score 0..100
        sentiment = (price_score + volume_score - 25) / 25  # -1..1

        score = (sentiment + 1) * 50
        return {
            "status": "ok",
            "engine": self.name,
            "score": round(float(score), 2),
            "sentiment": round(float(sentiment), 4),
            "breakdown": {
                "price_score": round(float(price_score), 2),
                "volume_score": round(float(volume_score), 2),
            },
        }
