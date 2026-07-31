"""Global Market Engine (Fase 2).

Menggunakan Yahoo Finance untuk bursa utama dunia.
Output: global_market_score dan global_risk_appetite.
"""

from __future__ import annotations

import pandas as pd

from trading_system.config import DEFAULT_GLOBAL_TICKERS
from trading_system.data.acquisition import YahooFinanceAdapter, normalize_ohlcv
from trading_system.data.storage import DataStorage
from trading_system.data.validation import DataQualityValidator


class GlobalMarketEngine:
    name = "global"

    def __init__(self, storage: DataStorage | None = None):
        self.storage = storage or DataStorage()
        self.adapter = YahooFinanceAdapter()
        self.validator = DataQualityValidator()

    def ensure_data(self, period: str = "2y", max_age_days: int = 1):
        """Fetch data if empty or stale (§4.2 SARAN_PENGEMBANGAN.md).

        Refresh jika umur data > ``max_age_days`` hari bursa.
        """
        from datetime import datetime, timezone, timedelta

        for label, ticker in DEFAULT_GLOBAL_TICKERS.items():
            df = self.storage.load_ohlcv(ticker)
            need_fetch = df.empty
            if not df.empty:
                last_ts = df.index[-1]
                if hasattr(last_ts, "tzinfo") and last_ts.tzinfo is None:
                    last_ts = last_ts.tz_localize("UTC")
                age = datetime.now(timezone.utc) - last_ts
                if age > timedelta(days=max_age_days):
                    need_fetch = True
            if need_fetch:
                result = self.adapter.fetch(ticker, period=period)
                if result["status"] == "ok":
                    raw = normalize_ohlcv(result["records"])
                    clean, _ = self.validator.validate(raw)
                    self.storage.save_ohlcv(clean)

    def load_index_data(self, ticker: str) -> pd.DataFrame:
        return self.storage.load_ohlcv(ticker)

    def compute_score(self) -> tuple[float, dict]:
        self.ensure_data()
        scores = {}
        above_50ma = 0
        above_200ma = 0
        total = 0

        for label, ticker in DEFAULT_GLOBAL_TICKERS.items():
            df = self.load_index_data(ticker)
            if df.empty:
                continue
            df["ma_50"] = df["close"].rolling(50).mean()
            df["ma_200"] = df["close"].rolling(200).mean()
            last = df.iloc[-1]
            total += 1
            if not pd.isna(last.get("ma_50")) and last["close"] > last["ma_50"]:
                above_50ma += 1
            if not pd.isna(last.get("ma_200")) and last["close"] > last["ma_200"]:
                above_200ma += 1

        if total == 0:
            return 50, {"global_above_50ma": 0, "global_above_200ma": 0}

        scores["above_50ma"] = (above_50ma / total) * 50
        scores["above_200ma"] = (above_200ma / total) * 50
        total_score = scores["above_50ma"] + scores["above_200ma"]
        return total_score, {**scores, "total_indices": total}

    def analyze(self, period: str = "2y") -> dict:
        score, breakdown = self.compute_score()

        # Data age tracking (§4.2)
        from datetime import datetime, timezone
        data_ages = {}
        for label, ticker in DEFAULT_GLOBAL_TICKERS.items():
            df = self.load_index_data(ticker)
            if not df.empty:
                last_ts = df.index[-1]
                if hasattr(last_ts, "tzinfo") and last_ts.tzinfo is None:
                    last_ts = last_ts.tz_localize("UTC")
                age = (datetime.now(timezone.utc) - last_ts).days
                data_ages[label] = age
            else:
                data_ages[label] = None
        breakdown["data_age_days"] = data_ages

        return {
            "status": "ok",
            "engine": self.name,
            "score": round(score, 2),
            "breakdown": breakdown,
        }
