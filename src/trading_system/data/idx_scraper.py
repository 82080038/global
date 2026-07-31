"""IDX scraper — adaptasi dari data_pasar_modal/ai_engine/scrape_idx_*.py.

Scrape data dari idx.co.id API:
- Foreign flow per stock (getStockSummary)
- Broker flow per stock

Data disimpan ke Parquet archive dan opsional ke SQLite.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from trading_system.config import DATA_ARCHIVE_DIR

try:
    import cloudscraper
except ImportError:
    cloudscraper = None

IDX_BASE = "https://www.idx.co.id"
HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.idx.co.id/id/data-pasar/ringkasan-perdagangan/ringkasan-saham/",
}

DEFAULT_STOCKS = [
    "ADRO", "AKRA", "ANTM", "ASII", "ASMI", "AUTO", "BBCA", "BBNI", "BBRI", "BFIN",
    "BMRI", "BRIS", "BSDE", "BTPS", "BULL", "CPIN", "CTRA", "DVLA", "EMTK", "EXCL",
    "GGRM", "GIAA", "GOTO", "ICBP", "INCO", "INDF", "ISAT", "JKON", "KLBF", "LPKR",
    "MDKA", "MEDC", "MERK", "MTDL", "MTLA", "MYOR", "PGAS", "PNLF", "PTBA", "SMGR",
    "SMMT", "TINS", "TLKM", "TOTL", "TOWR", "UNVR", "WSBP",
]


def get_trading_dates(start_date: str = "2020-01-02", end_date: str | None = None) -> list[str]:
    """Generate weekdays between start and end dates (YYYYMMDD format)."""
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    dates = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            dates.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)
    return dates


def fetch_stock_summary(scraper, date_str: str) -> list[dict] | None:
    """Fetch per-stock summary for a given date from IDX."""
    url = f"{IDX_BASE}/primary/TradingSummary/getStockSummary?date={date_str}"
    r = scraper.get(url, headers=HEADERS, timeout=15)
    if r.status_code != 200:
        return None
    try:
        data = r.json()
        if data.get("recordsTotal", 0) > 0:
            return data.get("data", [])
    except Exception:
        pass
    return None


def scrape_foreign_flow(
    start_date: str = "2020-01-02",
    end_date: str | None = None,
    stocks: list[str] | None = None,
    archive_dir: Path | None = None,
    delay: float = 0.3,
) -> pd.DataFrame:
    """Scrape foreign flow data from IDX.co.id.

    Args:
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD). Default: today.
        stocks: List of stock codes to filter. Default: DEFAULT_STOCKS.
        archive_dir: Directory to save Parquet. Default: DATA_ARCHIVE_DIR.
        delay: Delay between requests in seconds.

    Returns:
        DataFrame with foreign flow data.
    """
    if cloudscraper is None:
        raise ImportError("cloudscraper is required. Install with: pip install cloudscraper")

    stocks = stocks or DEFAULT_STOCKS
    stock_set = set(stocks)
    archive_dir = archive_dir or DATA_ARCHIVE_DIR
    scraper = cloudscraper.create_scraper()

    dates = get_trading_dates(start_date, end_date)
    print(f"Scraping foreign flow: {len(dates)} trading dates from {start_date} to {end_date or 'today'}")

    all_rows = []
    for i, date_str in enumerate(dates):
        stocks_data = fetch_stock_summary(scraper, date_str)
        if not stocks_data:
            continue

        date_fmt = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        for row in stocks_data:
            kode = row.get("StockCode", "").strip()
            if kode not in stock_set:
                continue
            all_rows.append({
                "tanggal": date_fmt,
                "kode": kode,
                "foreign_buy": int(row.get("ForeignBuy", 0)),
                "foreign_sell": int(row.get("ForeignSell", 0)),
                "foreign_net": int(row.get("ForeignBuy", 0)) - int(row.get("ForeignSell", 0)),
                "volume": int(row.get("Volume", 0)),
                "value": int(row.get("Value", 0)),
            })

        if (i + 1) % 100 == 0:
            print(f"  Progress: {i+1}/{len(dates)} dates, {len(all_rows)} records")

        time.sleep(delay)

    df = pd.DataFrame(all_rows)
    if not df.empty:
        out_dir = archive_dir / "foreign_flow_idx"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"foreign_flow_idx_{datetime.now().strftime('%Y%m%d')}.parquet"
        df.to_parquet(out_file, index=False, compression="snappy")
        print(f"Saved {len(df)} records to {out_file}")

    return df
