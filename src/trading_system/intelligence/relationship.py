"""Market Relationship Engine (Fase 3).

Menghitung rolling correlation dan lag antara saham dan aset global/macro.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trading_system.config import DEFAULT_BENCHMARK, DEFAULT_GLOBAL_TICKERS, DEFAULT_MACRO_TICKERS
from trading_system.data.storage import DataStorage


class MarketRelationshipEngine:
    name = "relationship"

    def __init__(self, storage: DataStorage | None = None, window: int = 60):
        self.storage = storage or DataStorage()
        self.window = window

    def compute_returns(self, ticker: str) -> pd.Series:
        df = self.storage.load_ohlcv(ticker)
        if df.empty:
            return pd.Series(dtype=float)
        return df["close"].pct_change().dropna()

    def lag_analysis(self, a: pd.Series, b: pd.Series, max_lag: int = 5) -> tuple[int, float]:
        """Return lag yang memberikan korelasi tertinggi (a vs b shift)."""
        common = a.index.intersection(b.index)
        x = a.loc[common]
        best_corr = -np.inf
        best_lag = 0
        for lag in range(-max_lag, max_lag + 1):
            y = b.shift(lag).loc[common]
            valid = x.notna() & y.notna()
            if valid.sum() < 10:
                continue
            corr = x[valid].corr(y[valid])
            if not np.isnan(corr) and corr > best_corr:
                best_corr = corr
                best_lag = lag
        return best_lag, float(best_corr) if not np.isnan(best_corr) else 0.0

    def rolling_correlation(self, a: pd.Series, b: pd.Series) -> float:
        common = a.index.intersection(b.index)
        if len(common) < self.window:
            return 0.0
        x = a.loc[common].iloc[-self.window:]
        y = b.loc[common].iloc[-self.window:]
        if x.empty or y.empty:
            return 0.0
        corr = x.corr(y)
        return float(corr) if not np.isnan(corr) else 0.0

    def compute(self, ticker: str) -> dict:
        a = self.compute_returns(ticker)
        if a.empty:
            return {"status": "error", "message": f"No OHLCV for {ticker}"}

        relationships = []
        for label, other in {**DEFAULT_GLOBAL_TICKERS, **DEFAULT_MACRO_TICKERS, "IHSG": DEFAULT_BENCHMARK}.items():
            b = self.compute_returns(other)
            if b.empty:
                continue
            corr = self.rolling_correlation(a, b)
            lag, _ = self.lag_analysis(a, b)
            self.storage.save_relationship(ticker, other, self.window, corr, lag)
            relationships.append({
                "asset": label,
                "ticker": other,
                "correlation": round(corr, 4),
                "lag": lag,
            })

        # Hitung influence score sederhana: rata-rata abs correlation
        influence = sum(abs(r["correlation"]) for r in relationships) / len(relationships) if relationships else 0

        return {
            "status": "ok",
            "engine": self.name,
            "score": round(influence * 100, 2),  # score 0-100 seberapa dipengaruhi pasar global
            "window": self.window,
            "relationships": relationships,
        }
