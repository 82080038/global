"""Import legacy data from Parquet archive to SQLite (§11.4b SARAN_PENGEMBANGAN.md).

Reads Parquet files from K:\\trading_data\\raw\\ (or DATA_ARCHIVE_DIR),
maps columns to the new SQLite schema, and imports data.

Usage:
    python -m scripts.import_legacy_data --all
    python -m scripts.import_legacy_data --table macro
    python -m scripts.import_legacy_data --table saham --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

# Ensure src is importable
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trading_system.config import DATA_ARCHIVE_DIR, DB_PATH
from trading_system.data.storage import DataStorage


# Mapping: Parquet table name → (SQLite table name, column mapping)
# column_mapping: {parquet_col: sqlite_col}
# If a column is not in the mapping, it's passed through as-is.
TABLE_MAPPING = {
    "macro": {
        "sqlite_table": "macro_data",
    },
    "saham": {
        "sqlite_table": "instrument_master",
    },
    "fundamental": {
        "sqlite_table": "fundamental_data",
    },
    "foreign_flow": {
        "sqlite_table": "foreign_flow",
    },
    "broker_flow": {
        "sqlite_table": "broker_flow",
    },
    "kebijakan_regulasi": {
        "sqlite_table": "policy_events",
    },
    "corporate_action": {
        "sqlite_table": "corporate_actions_legacy",
    },
    "sektor": {
        "sqlite_table": "sector_master",
    },
    "fear_greed_index": {
        "sqlite_table": "fear_greed",
    },
    "event_eksternal": {
        "sqlite_table": "external_events",
    },
    "esg_scores": {
        "sqlite_table": "esg_scores",
    },
    "corporate_governance": {
        "sqlite_table": "corporate_governance",
    },
    "stock_personality": {
        "sqlite_table": "stock_personality",
    },
    "ai_scores": {
        "sqlite_table": "ai_scores_historical",
    },
    "ai_alerts": {
        "sqlite_table": "alerts_historical",
    },
    "backtest_result": {
        "sqlite_table": "backtest_results",
    },
    "trade_journal": {
        "sqlite_table": "trade_journal",
    },
    "pattern_analysis": {
        "sqlite_table": "pattern_analysis",
    },
    "indikator_teknikal": {
        "sqlite_table": "technical_indicators",
    },
}

# Tables that have UNIQUE constraints — use INSERT OR REPLACE
UNIQUE_TABLES = {
    "instrument_master",  # kode UNIQUE
    "sector_master",  # kode UNIQUE
    "fear_greed",  # tanggal UNIQUE
    "fundamental_data",  # UNIQUE(kode, periode)
    "esg_scores",  # UNIQUE(kode, year, rating_agency)
    "corporate_governance",  # UNIQUE(kode, year)
    "technical_indicators",  # UNIQUE(kode, tanggal)
}


def load_parquet_table(parquet_dir: Path, table_name: str) -> pd.DataFrame:
    """Load all parquet files for a table from the archive directory."""
    table_dir = parquet_dir / table_name
    if not table_dir.exists():
        return pd.DataFrame()

    parquet_files = sorted(table_dir.glob("*.parquet"))
    if not parquet_files:
        return pd.DataFrame()

    dfs = []
    for f in parquet_files:
        df = pd.read_parquet(f)
        dfs.append(df)

    result = pd.concat(dfs, ignore_index=True)
    return result


def convert_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Convert date/timestamp columns to string for SQLite."""
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime("%Y-%m-%d %H:%M:%S")
        elif df[col].dtype == "object":
            # Try converting string dates
            try:
                parsed = pd.to_datetime(df[col], errors="raise", format="%Y-%m-%d")
                df[col] = parsed.dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass
    return df


def import_table(
    storage: DataStorage,
    parquet_dir: Path,
    parquet_name: str,
    sqlite_table: str,
    dry_run: bool = False,
) -> dict:
    """Import a single table from Parquet to SQLite."""
    df = load_parquet_table(parquet_dir, parquet_name)
    if df.empty:
        return {"status": "empty", "table": parquet_name, "rows": 0}

    # Convert dates to strings
    df = convert_dates(df)

    # Drop columns that don't exist in SQLite schema
    with storage._connect() as conn:
        cur = conn.execute(f"PRAGMA table_info({sqlite_table})")
        sqlite_cols = {r[1] for r in cur.fetchall()}

    # Keep only columns that exist in both
    common_cols = [c for c in df.columns if c in sqlite_cols]
    df = df[common_cols]

    if dry_run:
        return {
            "status": "dry_run",
            "table": parquet_name,
            "sqlite_table": sqlite_table,
            "rows": len(df),
            "columns": list(df.columns),
        }

    # Import
    with storage._connect() as conn:
        if sqlite_table in UNIQUE_TABLES:
            method = "REPLACE"
        else:
            method = "APPEND"

        df.to_sql(sqlite_table, conn, if_exists="append", index=False, method="multi", chunksize=500)

    return {
        "status": "ok",
        "table": parquet_name,
        "sqlite_table": sqlite_table,
        "rows": len(df),
        "columns": list(df.columns),
    }


def main():
    parser = argparse.ArgumentParser(description="Import legacy data from Parquet to SQLite")
    parser.add_argument("--all", action="store_true", help="Import all tables")
    parser.add_argument("--table", type=str, help="Specific Parquet table to import")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be imported without writing")
    parser.add_argument("--archive-dir", type=str, default=str(DATA_ARCHIVE_DIR), help="Parquet archive directory")
    args = parser.parse_args()

    parquet_dir = Path(args.archive_dir)
    if not parquet_dir.exists():
        print(f"ERROR: Archive directory not found: {parquet_dir}")
        sys.exit(1)

    storage = DataStorage()

    if args.all:
        tables = list(TABLE_MAPPING.keys())
    elif args.table:
        tables = [args.table]
    else:
        parser.print_help()
        sys.exit(1)

    print(f"Archive: {parquet_dir}")
    print(f"Database: {DB_PATH}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'IMPORT'}")
    print("-" * 60)

    total_rows = 0
    for parquet_name in tables:
        if parquet_name not in TABLE_MAPPING:
            print(f"  SKIP  {parquet_name} — no mapping defined")
            continue

        sqlite_table = TABLE_MAPPING[parquet_name]["sqlite_table"]
        result = import_table(storage, parquet_dir, parquet_name, sqlite_table, dry_run=args.dry_run)

        status = result["status"]
        rows = result["rows"]
        total_rows += rows if status == "ok" else 0

        if status == "empty":
            print(f"  EMPTY {parquet_name} → {sqlite_table} (no parquet files)")
        elif status == "dry_run":
            print(f"  PREV  {parquet_name} → {sqlite_table}: {rows} rows, cols: {result['columns']}")
        else:
            print(f"  OK    {parquet_name} → {sqlite_table}: {rows} rows imported")

    print("-" * 60)
    print(f"Total rows imported: {total_rows}")


if __name__ == "__main__":
    main()
