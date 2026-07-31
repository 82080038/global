"""Data Acquisition Engine (Phase 1).

Menggunakan Yahoo Finance (yfinance) sebagai sumber sementara.
Untuk saham Indonesia, gunakan suffix .JK (mis. BBCA.JK, TLKM.JK).
"""

import threading
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import yfinance as yf

from trading_system.config import RAW_ZONE, YFINANCE_RATE_LIMIT_CALLS, YFINANCE_RATE_LIMIT_WINDOW
from trading_system.data.rate_limit import YFinanceRateLimiter
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


class DataSourceAdapter(ABC):
    """Abstract base class untuk semua data source adapters (§4.1).

    Setiap adapter harus implement fetch() dan fetch_incremental().
    Ini memungkinkan multiple data sources (Yahoo Finance, IDX scraper, dll.)
    dengan interface yang seragam.
    """

    name: str = "base"

    @abstractmethod
    def fetch(
        self,
        ticker: str,
        period: str = "2y",
        interval: str = "1d",
    ) -> dict[str, Any]:
        """Fetch full historical data for a ticker.

        Returns dict with keys: status, records, message.
        """
        ...

    def fetch_incremental(
        self,
        ticker: str,
        last_timestamp: str | None = None,
        interval: str = "1d",
    ) -> dict[str, Any]:
        """Fetch only data newer than last_timestamp (incremental fetch).

        If last_timestamp is None, falls back to full fetch.
        Default implementation: compute period from last_timestamp and call fetch().
        Subclasses can override for more efficient incremental fetching.
        """
        if last_timestamp is None:
            return self.fetch(ticker, period="2y", interval=interval)

        # Calculate how many days since last fetch
        try:
            last_dt = pd.to_datetime(last_timestamp)
            if last_dt.tzinfo is None:
                last_dt = last_dt.tz_localize(UTC)
            else:
                last_dt = last_dt.tz_convert(UTC)
            days_since = (datetime.now(UTC) - last_dt).days
            if days_since <= 1:
                period = "5d"
            elif days_since <= 30:
                period = "1mo"
            elif days_since <= 90:
                period = "3mo"
            elif days_since <= 180:
                period = "6mo"
            elif days_since <= 365:
                period = "1y"
            else:
                period = "2y"
        except Exception:
            period = "2y"

        return self.fetch(ticker, period=period, interval=interval)


class YahooFinanceAdapter(DataSourceAdapter):
    """Adapter Yahoo Finance — implementasi DataSourceAdapter."""

    name = "yahoo_finance"

    def __init__(self, rate_limiter: YFinanceRateLimiter | None = None):
        self.storage = DataStorage()
        self.rate_limiter = rate_limiter or YFinanceRateLimiter.from_env()

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
        def _do_fetch():
            t = yf.Ticker(ticker)
            df = t.history(period=period, interval=interval, auto_adjust=False)
            if df.empty:
                return pd.DataFrame()
            return df

        result = self.rate_limiter.execute(ticker, _do_fetch)

        if result.error:
            self.storage.update_source_health(self.name, "down", success=False)
            self.storage.audit(
                "data.raw.ohlcv.error",
                {"ticker": ticker, "error": result.error, "attempts": result.attempts},
            )
            return {"status": "error", "records": pd.DataFrame(), "message": result.error}

        df = result.data
        if df is None or df.empty:
            return {"status": "empty", "records": pd.DataFrame(), "message": "No data returned"}

        try:
            df.reset_index(inplace=True)
            df.rename(
                columns={
                    "Date": "timestamp",
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Adj Close": "adjusted_close",
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
            df["ingested_at"] = datetime.now(UTC).isoformat()

            raw_file = RAW_ZONE / f"{ticker}_{interval}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.parquet"
            df.to_parquet(raw_file, index=False)

            self.storage.update_source_health(self.name, "ok", success=True)
            self.storage.audit(
                "data.raw.ohlcv",
                {"ticker": ticker, "period": period, "rows": len(df), "raw_file": str(raw_file)},
            )

            # Auto-fetch corporate actions and update adjusted_close (P2-1, §4.3)
            try:
                from trading_system.corporate.actions import CorporateActionEngine
                ca_engine = CorporateActionEngine(self.storage)
                ca_engine.fetch(ticker)
                self.storage.update_adjusted_close(ticker)
            except Exception:
                pass  # non-fatal: adjusted_close defaults to close

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

    if "adj_close" in df.columns:
        df["adjusted_close"] = df["adj_close"]
    else:
        df["adjusted_close"] = df["close"]
    df["data_quality_score"] = None
    cols = [
        "ticker", "asset_class", "exchange", "timestamp", "timeframe",
        "open", "high", "low", "close", "volume", "adjusted_close",
        "source", "ingested_at", "data_quality_score",
    ]
    return df[[c for c in cols if c in df.columns]]


class SQLiteAdapter(DataSourceAdapter):
    """Adapter for importing OHLCV data from a legacy SQLite database.

    Reads from a source SQLite DB (e.g., pasar_modal/data/saham.db)
    and normalizes to the global schema.
    """

    name = "sqlite_import"

    def __init__(self, source_db_path: str, storage: DataStorage | None = None):
        self.source_db_path = source_db_path
        self.storage = storage or DataStorage()

    def fetch(
        self,
        ticker: str,
        period: str = "2y",
        interval: str = "1d",
    ) -> dict[str, Any]:
        """Fetch OHLCV data from source SQLite DB."""
        import sqlite3

        try:
            conn = sqlite3.connect(self.source_db_path)
            query = "SELECT * FROM ohlcv WHERE ticker = ?"
            params: list = [ticker]

            if period != "max":
                days_map = {"5d": 5, "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730}
                days = days_map.get(period, 730)
                start_date = (datetime.now() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
                query += " AND date >= ?"
                params.append(start_date)

            query += " ORDER BY date"
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()

            if df.empty:
                return {"status": "empty", "records": pd.DataFrame(), "message": "No data"}

            df = self._normalize(df, ticker)
            return {"status": "ok", "records": df, "message": f"Imported {len(df)} rows"}
        except Exception as e:
            return {"status": "error", "records": pd.DataFrame(), "message": str(e)}

    def fetch_incremental(
        self,
        ticker: str,
        last_timestamp: str | None = None,
        interval: str = "1d",
    ) -> dict[str, Any]:
        """Fetch only rows newer than last_timestamp from source DB."""
        import sqlite3

        try:
            conn = sqlite3.connect(self.source_db_path)
            if last_timestamp:
                df = pd.read_sql_query(
                    "SELECT * FROM ohlcv WHERE ticker = ? AND date > ? ORDER BY date",
                    conn, params=[ticker, last_timestamp],
                )
            else:
                df = pd.read_sql_query(
                    "SELECT * FROM ohlcv WHERE ticker = ? ORDER BY date",
                    conn, params=[ticker],
                )
            conn.close()

            if df.empty:
                return {"status": "empty", "records": pd.DataFrame(), "message": "No new data"}

            df = self._normalize(df, ticker)
            return {"status": "ok", "records": df, "message": f"Imported {len(df)} new rows"}
        except Exception as e:
            return {"status": "error", "records": pd.DataFrame(), "message": str(e)}

    def _normalize(self, df: pd.DataFrame, ticker: str) -> pd.DataFrame:
        """Normalize source DB columns to global schema."""
        df = df.copy()
        col_map = {
            "date": "timestamp", "Date": "timestamp",
            "adj_close": "adjusted_close", "Adj Close": "adjusted_close",
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        }
        df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)

        if "adjusted_close" not in df.columns:
            df["adjusted_close"] = df.get("close", 0)
        if "ticker" not in df.columns:
            df["ticker"] = ticker
        df["source"] = self.name
        df["ingested_at"] = datetime.now(UTC).isoformat()
        df["asset_class"] = "equity"
        df["exchange"] = "IDX" if ticker.endswith(".JK") else "GLOBAL"
        df["timeframe"] = "1d"
        df["data_quality_score"] = None
        return df


class CSVAdapter(DataSourceAdapter):
    """Adapter for importing OHLCV data from CSV files.

    Expects columns: ticker, timestamp/date, open, high, low, close, volume.
    """

    name = "csv_import"

    def __init__(self, csv_path: str, storage: DataStorage | None = None):
        self.csv_path = csv_path
        self.storage = storage or DataStorage()

    def fetch(
        self,
        ticker: str,
        period: str = "2y",
        interval: str = "1d",
    ) -> dict[str, Any]:
        """Fetch OHLCV data from CSV file, filtered by ticker."""
        try:
            df = pd.read_csv(self.csv_path)
            if "ticker" in df.columns:
                df = df[df["ticker"] == ticker]
            elif "kode" in df.columns:
                df = df[df["kode"] == ticker]

            if df.empty:
                return {"status": "empty", "records": pd.DataFrame(), "message": "No data"}

            df = self._normalize(df, ticker)
            return {"status": "ok", "records": df, "message": f"Imported {len(df)} rows"}
        except Exception as e:
            return {"status": "error", "records": pd.DataFrame(), "message": str(e)}

    def fetch_incremental(
        self,
        ticker: str,
        last_timestamp: str | None = None,
        interval: str = "1d",
    ) -> dict[str, Any]:
        """Fetch rows newer than last_timestamp from CSV."""
        result = self.fetch(ticker, period="max", interval=interval)
        if result["status"] != "ok":
            return result

        df = result["records"]
        if last_timestamp and not df.empty:
            df = df[df["timestamp"] > last_timestamp]
            if df.empty:
                return {"status": "empty", "records": pd.DataFrame(), "message": "No new data"}

        return {"status": "ok", "records": df, "message": f"Imported {len(df)} new rows"}

    def _normalize(self, df: pd.DataFrame, ticker: str) -> pd.DataFrame:
        """Normalize CSV columns to global schema."""
        df = df.copy()
        col_map = {
            "date": "timestamp", "Date": "timestamp",
            "kode": "ticker",
            "adj_close": "adjusted_close", "Adj Close": "adjusted_close",
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        }
        df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)

        if "adjusted_close" not in df.columns:
            df["adjusted_close"] = df.get("close", 0)
        if "ticker" not in df.columns:
            df["ticker"] = ticker
        df["source"] = self.name
        df["ingested_at"] = datetime.now(UTC).isoformat()
        df["asset_class"] = "equity"
        df["exchange"] = "IDX" if ticker.endswith(".JK") else "GLOBAL"
        df["timeframe"] = "1d"
        df["data_quality_score"] = None
        return df


class DataSourceManager:
    """Multi-source data manager — routes fetch requests to registered adapters.

    Supports priority-based fallback: if primary source fails, try next.
    Also provides incremental fetch with automatic last_timestamp lookup.
    """

    def __init__(self, storage: DataStorage | None = None):
        self.storage = storage or DataStorage()
        self._adapters: dict[str, DataSourceAdapter] = {}
        self._priority: list[str] = []

    def register(self, adapter: DataSourceAdapter, priority: int = 0):
        """Register an adapter with a priority (lower = higher priority)."""
        self._adapters[adapter.name] = adapter
        self._priority.append(adapter.name)
        self._priority.sort(key=lambda name: priority if name == adapter.name else 0)

    def fetch(
        self,
        ticker: str,
        period: str = "2y",
        interval: str = "1d",
        source: str | None = None,
    ) -> dict[str, Any]:
        """Fetch data from a specific source or try all sources by priority."""
        if source and source in self._adapters:
            return self._adapters[source].fetch(ticker, period, interval)

        errors = []
        for name in self._priority:
            adapter = self._adapters[name]
            result = adapter.fetch(ticker, period, interval)
            if result["status"] == "ok":
                return result
            errors.append(f"{name}: {result.get('message', 'unknown')}")

        return {
            "status": "error",
            "records": pd.DataFrame(),
            "message": f"All sources failed: {'; '.join(errors)}",
        }

    def fetch_incremental(
        self,
        ticker: str,
        interval: str = "1d",
        source: str | None = None,
    ) -> dict[str, Any]:
        """Fetch only new data since the last stored timestamp.

        Automatically queries the storage for the last timestamp for this ticker.
        """
        last_ts = self._get_last_timestamp(ticker, interval)

        if source and source in self._adapters:
            return self._adapters[source].fetch_incremental(ticker, last_ts, interval)

        errors = []
        for name in self._priority:
            adapter = self._adapters[name]
            result = adapter.fetch_incremental(ticker, last_ts, interval)
            if result["status"] == "ok":
                return result
            errors.append(f"{name}: {result.get('message', 'unknown')}")

        return {
            "status": "error",
            "records": pd.DataFrame(),
            "message": f"All sources failed: {'; '.join(errors)}",
        }

    def _get_last_timestamp(self, ticker: str, timeframe: str = "1d") -> str | None:
        """Get the last timestamp for a ticker from storage."""
        df = self.storage.load_ohlcv(ticker, timeframe=timeframe)
        if df.empty:
            return None
        return str(df.index[-1]) if hasattr(df.index, "__getitem__") else str(df["timestamp"].iloc[-1])

    @property
    def sources(self) -> list[str]:
        """List registered source names."""
        return list(self._adapters.keys())
