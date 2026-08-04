"""Bootstrap: Load ALL data from Parquet archive into SQLite.

Used when setting up the application on a new computer:
1. Copy Parquet archive (e.g. E:\\trading_data\\archive\\) to new machine
2. Set DATA_ARCHIVE_DIR in .env to the archive path
3. Run: python scripts/bootstrap_from_parquet.py
4. SQLite DB will be populated with all data from Parquet

This loads:
- Per-ticker OHLCV files from archive/ohlcv/ (fast, one file per ticker)
- All other tables from archive/tables/{table}.parquet (single file per table)

Usage:
    python scripts/bootstrap_from_parquet.py                    # load all
    python scripts/bootstrap_from_parquet.py --tickers BBCA.JK  # specific tickers only
    python scripts/bootstrap_from_parquet.py --dry-run           # preview only
    python scripts/bootstrap_from_parquet.py --ohlcv-only        # skip table restore
    python scripts/bootstrap_from_parquet.py --tables-only        # skip OHLCV restore
"""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(line_buffering=True)

import pandas as pd
import sqlite3
from trading_system.config import DATA_ARCHIVE_DIR, DB_PATH
from trading_system.data.archive import ArchiveAdapter
from trading_system.data.storage import DataStorage
from trading_system.data.validation import DataQualityValidator
from trading_system.data.acquisition import normalize_ohlcv


def restore_tables(storage: DataStorage, dry_run: bool = False) -> dict:
    """Restore all non-OHLCV tables from archive/tables/*.parquet."""
    tables_dir = DATA_ARCHIVE_DIR / "tables"
    if not tables_dir.exists():
        print(f"  Tables directory not found: {tables_dir}")
        return {"restored": 0, "skipped": 0, "errors": 0}

    parquet_files = sorted(tables_dir.glob("*.parquet"))
    print(f"  Found {len(parquet_files)} table files")

    restored = 0
    skipped = 0
    errors = 0

    column_mappings = {
        "policy_events": {
            "tanggal": "date",
            "kategori": "event_type",
            "judul": "description",
            "instansi": "source",
            "dampak": "impact",
        },
    }

    for pf in parquet_files:
        table_name = pf.stem
        try:
            df = pd.read_parquet(pf)
            if df.empty:
                skipped += 1
                continue

            if table_name in column_mappings:
                df = df.rename(columns=column_mappings[table_name])
                for col in column_mappings[table_name].values():
                    if col not in df.columns:
                        df[col] = None

            if dry_run:
                print(f"    {table_name:30s} {len(df):>10,} rows (dry-run)")
                restored += 1
                continue

            conn = sqlite3.connect(str(DB_PATH))

            if table_name == "instrument_master":
                df.to_sql(table_name, conn, if_exists="replace", index=False)
            elif table_name == "ohlcv":
                skipped += 1
                conn.close()
                continue
            else:
                conn.execute(f"DELETE FROM {table_name}")
                df.to_sql(table_name, conn, if_exists="append", index=False)

            conn.commit()
            conn.close()
            restored += 1
            print(f"    {table_name:30s} {len(df):>10,} rows OK")
        except Exception as e:
            errors += 1
            print(f"    {table_name:30s} ERROR: {e}")

    return {"restored": restored, "skipped": skipped, "errors": errors}


def restore_ohlcv(archive: ArchiveAdapter, storage: DataStorage,
                  validator: DataQualityValidator, tickers: list[str],
                  dry_run: bool = False) -> dict:
    """Restore OHLCV from per-ticker Parquet files."""
    loaded = 0
    skipped = 0
    errors = 0
    total_rows = 0

    for i, ticker in enumerate(tickers):
        try:
            df = archive.load_ohlcv(ticker)
            if df.empty:
                skipped += 1
                continue

            if dry_run:
                if (i + 1) % 100 == 0 or (i + 1) == len(tickers):
                    print(f"  [{i+1}/{len(tickers)}] {ticker}: {len(df):,} rows (dry-run)")
                loaded += 1
                total_rows += len(df)
                continue

            df = df.reset_index()
            if "ticker" not in df.columns:
                df["ticker"] = ticker
            if "asset_class" not in df.columns:
                df["asset_class"] = "equity"
            if "exchange" not in df.columns:
                df["exchange"] = "INDO" if ticker.endswith(".JK") else "GLOBAL"
            if "timeframe" not in df.columns:
                df["timeframe"] = "1d"
            if "source" not in df.columns:
                df["source"] = "archive"
            if "ingested_at" not in df.columns:
                df["ingested_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")
            if "data_quality_score" not in df.columns:
                df["data_quality_score"] = None

            raw = normalize_ohlcv(df)
            clean, report = validator.validate(raw)

            if report.action == "pause":
                print(f"  [{i+1}/{len(tickers)}] {ticker}: SKIP (quality={report.data_quality_score})")
                skipped += 1
                continue

            n = storage.save_ohlcv(clean)
            loaded += 1
            total_rows += n

            if (i + 1) % 100 == 0 or (i + 1) == len(tickers):
                print(f"  [{i+1}/{len(tickers)}] {ticker}: {n:,} rows loaded (total: {total_rows:,})")

        except Exception as e:
            errors += 1
            print(f"  [{i+1}/{len(tickers)}] {ticker}: ERROR - {e}")

    return {"loaded": loaded, "skipped": skipped, "errors": errors, "total_rows": total_rows}


def main():
    parser = argparse.ArgumentParser(description="Bootstrap SQLite from Parquet archive")
    parser.add_argument("--tickers", nargs="*", default=None, help="Specific tickers (default: all in archive)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    parser.add_argument("--ohlcv-only", action="store_true", help="Only restore OHLCV, skip other tables")
    parser.add_argument("--tables-only", action="store_true", help="Only restore tables, skip OHLCV")
    args = parser.parse_args()

    archive = ArchiveAdapter()
    storage = DataStorage()
    validator = DataQualityValidator()

    print(f"{'=' * 70}")
    print(f"BOOTSTRAP: Parquet -> SQLite")
    print(f"Archive:  {DATA_ARCHIVE_DIR}")
    print(f"DB:       {DB_PATH}")
    print(f"{'=' * 70}")

    # Phase 1: Restore tables (non-OHLCV)
    if not args.ohlcv_only:
        print(f"\n--- Phase 1: Restore tables ---")
        t_result = restore_tables(storage, dry_run=args.dry_run)
        print(f"  Tables: {t_result['restored']} restored, {t_result['skipped']} skipped, {t_result['errors']} errors")

    # Phase 2: Restore OHLCV
    if not args.tables_only:
        print(f"\n--- Phase 2: Restore OHLCV ---")
        if args.tickers:
            tickers = args.tickers
        else:
            tickers = archive.list_archived_tickers()
        print(f"  Tickers to load: {len(tickers)}")

        o_result = restore_ohlcv(archive, storage, validator, tickers, dry_run=args.dry_run)
        print(f"  OHLCV: {o_result['loaded']} tickers loaded ({o_result['total_rows']:,} rows), "
              f"{o_result['skipped']} skipped, {o_result['errors']} errors")

    print(f"\n{'=' * 70}")
    print(f"Bootstrap complete at {datetime.now(UTC).isoformat()}")
    print(f"{'=' * 70}")
    print(f"\nNext steps:")
    print(f"  1. Run: python scripts/render_data.py --only fundamental  (fetch latest fundamentals)")
    print(f"  2. Run: python -m trading_system.cli schedule --once       (daily update)")
    print(f"  3. Start API:  uvicorn trading_system.api.app:app --reload")
    print(f"  4. Start frontend: cd frontend && npm run dev")


if __name__ == "__main__":
    main()
