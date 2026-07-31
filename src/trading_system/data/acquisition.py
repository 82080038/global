"""Data Acquisition Engine (Phase 1).

Menggunakan Yahoo Finance (yfinance) sebagai sumber sementara.
Untuk saham Indonesia, gunakan suffix .JK (mis. BBCA.JK, TLKM.JK).
"""

import threading
import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import yfinance as yf

from trading_system.config import RAW_ZONE, YFINANCE_RATE_LIMIT_CALLS, YFINANCE_RATE_LIMIT_WINDOW
from trading_system.data.storage import DataStorage


class RateLimiter:
    """Sliding window rate limiter untuk mencegah throttling dari Yahoo Finance."""

    def __init__(self, calls: int, window: float):
        self.calls = calls
        self.window = window
        self.timestamps: list[float] = []
        self.lock = threading.Lock()

    def acquire(self):
        with self.lock:
            now = time.time()
            # Bersihkan timestamp di luar window
            self.timestamps = [t for t in self.timestamps if now - t < self.window]

            if len(self.timestamps) >= self.calls:
                wait_until = self.timestamps[0] + self.window
                sleep_for = wait_until - now
                if sleep_for > 0:
                    time.sleep(sleep_for)

            # Catat waktu panggilan setelah tunggu
            self.timestamps.append(time.time())


# Instance global rate limiter untuk YFinance
_yfinance_rate_limiter = RateLimiter(
    calls=YFINANCE_RATE_LIMIT_CALLS,
    window=YFINANCE_RATE_LIMIT_WINDOW,
)


class YahooFinanceAdapter:
    """Adapter sederhana Yahoo Finance."""

    name = "yahoo_finance"

    def __init__(self):
        self.storage = DataStorage()

    def fetch(
        self,
        ticker: str,
        period: str = "2y",
        interval: str = "1d",
    ) -> dict[str, Any]:
        """Fetch data mentah dari Yahoo Finance.

        Returns
        -------
        dict dengan key: status, records, message
        """
        try:
            # Rate limiting sebelum memanggil YFinance
            _yfinance_rate_limiter.acquire()

            # Pastikan suffix .JK untuk IDX saat ini hard-code;
            # nanti mapping sumber akan di-source_config.yaml
            t = yf.Ticker(ticker)
            df = t.history(period=period, interval=interval)
            if df.empty:
                return {"status": "empty", "records": pd.DataFrame(), "message": "No data returned"}

            df.reset_index(inplace=True)
            df.rename(
                columns={
                    "Date": "timestamp",
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume",
                    "Stock Splits": "splits",
                    "Dividends": "dividends",
                },
                inplace=True,
            )
            df["ticker"] = ticker
            df["asset_class"] = "equity"
            df["exchange"] = "INDO" if ticker.endswith(".JK") else "GLOBAL"
            df["timeframe"] = interval
            df["source"] = self.name
            df["ingested_at"] = datetime.now(timezone.utc).isoformat()

            # Simpan raw zone sebagai parquet
            raw_file = RAW_ZONE / f"{ticker}_{interval}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.parquet"
            df.to_parquet(raw_file, index=False)

            self.storage.update_source_health(self.name, "ok", success=True)
            self.storage.audit(
                "data.raw.ohlcv",
                {"ticker": ticker, "period": period, "rows": len(df), "raw_file": str(raw_file)},
            )
            return {"status": "ok", "records": df, "message": f"Fetched {len(df)} rows"}
        except Exception as e:
            self.storage.update_source_health(self.name, "down", success=False)
            self.storage.audit(
                "data.raw.ohlcv.error",
                {"ticker": ticker, "error": str(e)},
            )
            return {"status": "error", "records": pd.DataFrame(), "message": str(e)}


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Normalisasi ke skema kontrak §4.1."""
    if df.empty:
        return df
    required = {"ticker", "open", "high", "low", "close", "volume", "source"}
    if not required.issubset(df.columns):
        raise ValueError(f"Kolom wajib hilang: {required - set(df.columns)}")

    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
    if "timestamp" in df.columns:
        df["timestamp"] = df["timestamp"].astype(str)
    if "ingested_at" in df.columns:
        df["ingested_at"] = pd.to_datetime(df["ingested_at"]).dt.tz_localize(None).astype(str)

    df["adjusted_close"] = df["close"]
    df["data_quality_score"] = None
    cols = [
        "ticker", "asset_class", "exchange", "timestamp", "timeframe",
        "open", "high", "low", "close", "volume", "adjusted_close",
        "source", "ingested_at", "data_quality_score",
    ]
    return df[[c for c in cols if c in df.columns]]
