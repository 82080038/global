"""Batch scraper untuk data idx.co.id."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from trading_system.config import DATA_ARCHIVE_DIR
from trading_system.data.adaptive_rate_limiter import AdaptiveRateLimiter
from trading_system.data.storage import DataStorage

try:
    from curl_cffi import requests as cffi_requests
except ImportError:
    cffi_requests = None

IDX_BASE = "https://www.idx.co.id"

STOCK_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.idx.co.id/id/data-pasar/ringkasan-perdagangan/ringkasan-saham/",
}

BROKER_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.idx.co.id/id/data-pasar/ringkasan-perdagangan/ringkasan-broker/",
}

DEFAULT_STOCKS = [
    "ADRO", "AKRA", "ANTM", "ASII", "ASMI", "AUTO", "BBCA", "BBNI", "BBRI", "BFIN",
    "BMRI", "BRIS", "BSDE", "BTPS", "BULL", "CPIN", "CTRA", "DVLA", "EMTK", "EXCL",
    "GGRM", "GIAA", "GOTO", "ICBP", "INCO", "INDF", "ISAT", "JKON", "KLBF", "LPKR",
    "MDKA", "MEDC", "MERK", "MTDL", "MTLA", "MYOR", "PGAS", "PNLF", "PTBA", "SMGR",
    "SMMT", "TINS", "TLKM", "TOTL", "TOWR", "UNVR", "WSBP",
]


def get_trading_dates(start: str, end: str | None = None) -> list[str]:
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")
    s = datetime.strptime(start, "%Y-%m-%d")
    e = datetime.strptime(end, "%Y-%m-%d")
    dates = []
    current = s
    while current <= e:
        if current.weekday() < 5:
            dates.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)
    return dates


def fmt_date(d: str) -> str:
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


def _extract_value(row: dict, *keys: str, default: float = 0.0) -> float:
    for k in keys:
        v = row.get(k)
        if v is not None and v != "":
            try:
                return float(str(v).replace(",", ""))
            except ValueError:
                return default
    return default


class IDXBatchEngine:
    def __init__(
        self,
        delay: float | None = None,
        timeout: float = 15.0,
        storage: DataStorage | None = None,
        archive_dir: Path | None = None,
        rate_limiter: AdaptiveRateLimiter | None = None,
    ):
        if cffi_requests is None:
            raise ImportError(
                "curl_cffi is required to bypass IDX Cloudflare. Install with: pip install curl_cffi"
            )
        self.timeout = timeout
        self.rate_limiter = rate_limiter or AdaptiveRateLimiter.for_idx_scraper()
        if delay is not None:
            self.rate_limiter._base_delay = delay
        self.storage = storage or DataStorage()
        self.source = "idx_scraper"
        self.archive_dir = archive_dir or DATA_ARCHIVE_DIR

    def _get(self, url: str, headers: dict | None = None, params: dict | None = None) -> dict:
        h = headers or STOCK_HEADERS
        last_err = None

        def _do_fetch():
            r = cffi_requests.get(url, headers=h, params=params, timeout=self.timeout, impersonate="chrome")
            if r.status_code == 200:
                return r.json()
            last_err_inner = f"HTTP {r.status_code}"
            raise RuntimeError(last_err_inner)

        result = self.rate_limiter.execute(url, _do_fetch)
        if result.error:
            raise RuntimeError(result.error)
        return result.data

    def _existing_dates(self, table: str, source: str) -> set[str]:
        with self.storage._connect() as conn:
            cur = conn.execute(
                f"SELECT DISTINCT date FROM {table} WHERE source = ?",
                (source,),
            )
            return {r[0] for r in cur.fetchall()}

    def _audit(self, event_type: str, payload: dict) -> None:
        self.storage.audit(event_type, payload)

    def _save_foreign_flow_rows(self, records: list[dict]) -> int:
        if not records:
            return 0
        # Quality gate: filter out records with negative or missing critical fields
        clean_records = [
            r for r in records
            if r.get("ticker")
            and r.get("date")
            and r["foreign_buy"] >= 0
            and r["foreign_sell"] >= 0
            and r["foreign_net"] is not None
        ]
        skipped = len(records) - len(clean_records)
        if skipped > 0:
            self._audit("data.idx.foreign_flow.quality_skip", {"skipped": skipped})
        tuples = [
            (
                r["ticker"],
                r["date"],
                r["foreign_buy"],
                r["foreign_sell"],
                r["foreign_net"],
                r["domestic_buy"],
                r["domestic_sell"],
                r["domestic_net"],
                r["source"],
            )
            for r in clean_records
        ]
        sql = """
            INSERT OR REPLACE INTO foreign_flow
            (ticker, date, foreign_buy, foreign_sell, foreign_net,
             domestic_buy, domestic_sell, domestic_net, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        return self.storage.executemany_batch(sql, tuples)

    def _save_broker_flow_rows(self, records: list[dict]) -> int:
        if not records:
            return 0
        # Quality gate: filter out records with missing critical fields or negative volumes
        clean_records = [
            r for r in records
            if r.get("broker")
            and r.get("date")
            and r["net_volume"] is not None
            and r["net_volume"] >= 0
        ]
        skipped = len(records) - len(clean_records)
        if skipped > 0:
            self._audit("data.idx.broker_flow.quality_skip", {"skipped": skipped})
        tuples = [
            (
                r["ticker"],
                r["date"],
                r["broker"],
                r["buy_volume"],
                r["buy_value"],
                r["sell_volume"],
                r["sell_value"],
                r["net_volume"],
                r["net_value"],
                r["source"],
            )
            for r in clean_records
        ]
        sql = """
            INSERT OR REPLACE INTO broker_flow
            (ticker, date, broker, buy_volume, buy_value, sell_volume,
             sell_value, net_volume, net_value, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        return self.storage.executemany_batch(sql, tuples)

    def _archive(self, df: pd.DataFrame, name: str) -> Path | None:
        if df.empty:
            return None
        out_dir = self.archive_dir / name
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{name}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.parquet"
        df.to_parquet(out_file, index=False, compression="snappy")
        return out_file

    def fetch_stock_summary(self, date_str: str) -> list[dict]:
        url = f"{IDX_BASE}/primary/TradingSummary/getStockSummary?date={date_str}"
        data = self._get(url)
        if not data.get("recordsTotal"):
            return []
        return data.get("data", [])

    def fetch_broker_summary(self, date_str: str) -> list[dict]:
        url = f"{IDX_BASE}/primary/TradingSummary/getBrokerSummary?date={date_str}"
        data = self._get(url, headers=BROKER_HEADERS)
        if not data.get("recordsTotal"):
            return []
        return data.get("data", [])

    def scrape_foreign_flow(
        self,
        start_date: str = "2020-01-02",
        end_date: str | None = None,
        tickers: list[str] | None = None,
        skip_existing: bool = True,
    ) -> dict[str, Any]:
        tickers = set(tickers or DEFAULT_STOCKS)
        dates = get_trading_dates(start_date, end_date)
        existing: set[str] = set()
        if skip_existing:
            existing = self._existing_dates("foreign_flow", self.source)

        total_dates = len(dates)
        saved = 0
        checked = 0
        all_records: list[dict] = []

        for i, d in enumerate(dates):
            if fmt_date(d) in existing:
                continue
            try:
                rows = self.fetch_stock_summary(d)
            except Exception as e:
                print(f"  [skip] {d}: {e}")
                continue
            if not rows:
                continue

            date_fmt = fmt_date(d)
            for row in rows:
                kode = row.get("StockCode", "").strip()
                if kode not in tickers:
                    continue

                fb = int(_extract_value(row, "ForeignBuy"))
                fs = int(_extract_value(row, "ForeignSell"))
                vol = int(_extract_value(row, "Volume"))
                val = int(_extract_value(row, "Value"))

                dom_buy = max(0, vol - fb)
                dom_sell = max(0, vol - fs)

                all_records.append({
                    "ticker": f"{kode}.JK" if "." not in kode else kode,
                    "date": date_fmt,
                    "foreign_buy": fb,
                    "foreign_sell": fs,
                    "foreign_net": fb - fs,
                    "domestic_buy": dom_buy,
                    "domestic_sell": dom_sell,
                    "domestic_net": dom_buy - dom_sell,
                    "source": self.source,
                })

            if (i + 1) % 100 == 0:
                n = self._save_foreign_flow_rows(all_records)
                saved += n
                all_records = []
                checked += 1

        n = self._save_foreign_flow_rows(all_records)
        saved += n

        df = pd.DataFrame(all_records)
        out_file = self._archive(df, "foreign_flow_idx")

        self.storage.update_source_health(self.source, "ok", success=True)
        self._audit("data.idx.foreign_flow", {
            "start": start_date,
            "end": end_date,
            "dates": total_dates,
            "saved": saved,
            "archive": str(out_file) if out_file else None,
        })

        return {
            "status": "ok",
            "dates_checked": total_dates,
            "records_saved": saved,
            "archive": out_file,
        }

    def scrape_broker_flow(
        self,
        start_date: str = "2020-01-02",
        end_date: str | None = None,
        skip_existing: bool = True,
    ) -> dict[str, Any]:
        dates = get_trading_dates(start_date, end_date)
        existing: set[str] = set()
        if skip_existing:
            existing = self._existing_dates("broker_flow", self.source)

        total_dates = len(dates)
        saved = 0
        all_records: list[dict] = []

        for i, d in enumerate(dates):
            if fmt_date(d) in existing:
                continue
            try:
                rows = self.fetch_broker_summary(d)
            except Exception as e:
                print(f"  [skip] {d}: {e}")
                continue
            if not rows:
                continue

            date_fmt = fmt_date(d)
            for row in rows:
                kode = (row.get("IDFirm") or row.get("BrokerCode") or row.get("code") or "").strip()
                if not kode:
                    continue

                # IDX getBrokerSummary returns aggregate Volume/Value per broker (no buy/sell split)
                vol = int(_extract_value(row, "Volume"))
                val = int(_extract_value(row, "Value"))

                all_records.append({
                    "ticker": "__MARKET__",
                    "date": date_fmt,
                    "broker": kode,
                    "buy_volume": 0,
                    "buy_value": 0,
                    "sell_volume": 0,
                    "sell_value": 0,
                    "net_volume": vol,
                    "net_value": val,
                    "source": self.source,
                })

            if (i + 1) % 100 == 0:
                n = self._save_broker_flow_rows(all_records)
                saved += n
                all_records = []

        n = self._save_broker_flow_rows(all_records)
        saved += n

        df = pd.DataFrame(all_records)
        out_file = self._archive(df, "broker_flow_idx")

        self.storage.update_source_health(self.source, "ok", success=True)
        self._audit("data.idx.broker_flow", {
            "start": start_date,
            "end": end_date,
            "dates": total_dates,
            "saved": saved,
            "archive": str(out_file) if out_file else None,
        })

        return {
            "status": "ok",
            "dates_checked": total_dates,
            "records_saved": saved,
            "archive": out_file,
        }
