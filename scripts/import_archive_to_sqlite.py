"""Import data dari Parquet archive ke SQLite sistem trading.

Membaca Parquet dari DATA_ARCHIVE_DIR dan mengisi tabel ohlcv di SQLite.
Hanya import data yang belum ada di SQLite (incremental).

Usage:
    python -m scripts.import_archive_to_sqlite
    python -m scripts.import_archive_to_sqlite --tickers BBCA TLKM ASII
    python -m scripts.import_archive_to_sqlite --archive-dir "K:\\trading_data\\raw"
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from trading_system.config import DATA_ARCHIVE_DIR, DB_PATH
from trading_system.data.storage import DataStorage


def load_archive_ohlcv(archive_dir: Path) -> pd.DataFrame:
    """Load all OHLCV Parquet files from archive."""
    ohlcv_dir = archive_dir / "ohlcv"
    if not ohlcv_dir.exists():
        print(f"  No ohlcv directory at {ohlcv_dir}")
        return pd.DataFrame()

    files = sorted(ohlcv_dir.glob("ohlcv_*.parquet"))
    if not files:
        print(f"  No Parquet files in {ohlcv_dir}")
        return pd.DataFrame()

    dfs = []
    for f in files:
        df = pd.read_parquet(f)
        dfs.append(df)
        print(f"  Loaded {f.name}: {len(df):,} rows")

    combined = pd.concat(dfs, ignore_index=True)
    return combined


def normalize_to_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize archive OHLCV to SQLite schema.

    Archive columns (from MySQL stock_history):
        kode, tanggal, open, high, low, close, volume, etc.

    SQLite schema expects:
        ticker, timestamp, open, high, low, close, volume,
        asset_class, exchange, timeframe, source, ingested_at
    """
    if df.empty:
        return df

    col_map = {
        "kode": "ticker",
        "tanggal": "timestamp",
        "date": "timestamp",
        "Date": "timestamp",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    required = {"ticker", "timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        print(f"  WARNING: Missing columns: {missing}")
        return pd.DataFrame()

    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d")
    df["asset_class"] = "equity"
    df["exchange"] = "IDX"
    df["timeframe"] = "1d"
    df["source"] = "archive"
    df["ingested_at"] = datetime.now(timezone.utc).isoformat()

    if ".JK" not in str(df["ticker"].iloc[0]):
        df["ticker"] = df["ticker"] + ".JK"

    keep = ["ticker", "timestamp", "open", "high", "low", "close", "volume",
            "asset_class", "exchange", "timeframe", "source", "ingested_at"]
    return df[[c for c in keep if c in df.columns]]


def import_ohlcv(archive_dir: Path, storage: DataStorage, tickers: list[str] | None = None) -> int:
    """Import OHLCV from archive to SQLite. Returns rows imported."""
    df = load_archive_ohlcv(archive_dir)
    if df.empty:
        return 0

    df = normalize_to_schema(df)
    if df.empty:
        return 0

    if tickers:
        ticker_set = {t if t.endswith(".JK") else t + ".JK" for t in tickers}
        df = df[df["ticker"].isin(ticker_set)]

    existing_tickers = set(storage.list_tickers())
    new_tickers = set(df["ticker"].unique()) - existing_tickers
    print(f"\n  Archive tickers: {df['ticker'].nunique()}")
    print(f"  Already in SQLite: {len(existing_tickers)}")
    print(f"  New tickers to import: {len(new_tickers)}")

    total = 0
    batch_size = 10000
    for i in range(0, len(df), batch_size):
        batch = df.iloc[i:i + batch_size]
        count = storage.save_ohlcv(batch)
        total += count
        print(f"  Saved batch {i//batch_size + 1}: {count:,} rows (total: {total:,})")

    return total


def import_saham_master(archive_dir: Path, storage: DataStorage) -> int:
    """Import master saham list from archive to SQLite watchlist."""
    saham_file = archive_dir / "saham" / "saham.parquet"
    if not saham_file.exists():
        print("  No saham master file found")
        return 0

    df = pd.read_parquet(saham_file)
    if df.empty:
        return 0

    kode_col = "kode" if "kode" in df.columns else df.columns[0]
    nama_col = "nama" if "nama" in df.columns else None
    sektor_col = "sektor" if "sektor" in df.columns else None

    imported = 0
    now = datetime.now(timezone.utc).isoformat()
    with storage._connect() as conn:
        for _, row in df.iterrows():
            ticker = str(row[kode_col])
            if not ticker.endswith(".JK"):
                ticker = ticker + ".JK"
            notes_parts = []
            if nama_col:
                notes_parts.append(str(row.get(nama_col, "")))
            if sektor_col:
                notes_parts.append(f"Sektor: {row.get(sektor_col, '')}")
            notes = " | ".join(notes_parts) if notes_parts else None

            try:
                conn.execute(
                    "INSERT OR IGNORE INTO watchlist (ticker, is_favorite, notes, created_at) VALUES (?, 0, ?, ?)",
                    (ticker, notes, now),
                )
                imported += 1
            except Exception:
                pass

    print(f"  Imported {imported} saham to watchlist")
    return imported


def main():
    parser = argparse.ArgumentParser(description="Import Parquet archive to SQLite")
    parser.add_argument(
        "--archive-dir",
        default=str(DATA_ARCHIVE_DIR),
        help="Archive directory path",
    )
    parser.add_argument(
        "--tickers",
        nargs="*",
        default=None,
        help="Specific tickers to import (default: all)",
    )
    parser.add_argument(
        "--skip-master",
        action="store_true",
        help="Skip importing saham master to watchlist",
    )
    args = parser.parse_args()

    archive_dir = Path(args.archive_dir)
    print(f"Archive: {archive_dir}")
    print(f"SQLite: {DB_PATH}")

    storage = DataStorage()

    if not args.skip_master:
        print("\n=== Importing saham master ===")
        import_saham_master(archive_dir, storage)

    print("\n=== Importing OHLCV ===")
    total = import_ohlcv(archive_dir, storage, args.tickers)

    print(f"\n{'='*60}")
    print(f"Total rows imported: {total:,}")
    print(f"Tickers in SQLite: {len(storage.list_tickers())}")


if __name__ == "__main__":
    main()
