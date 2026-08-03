"""Export all critical SQLite tables to Parquet files for portability.

Usage:
    python scripts/export_all_tables.py

Exports to: {DATA_ARCHIVE_DIR}/tables/{table_name}.parquet
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from trading_system.config import DATA_ARCHIVE_DIR

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "trading_system.db"

# Tables to export (data tables only, not system/internal)
EXPORT_TABLES = [
    "instrument_master",
    "ohlcv",
    "fundamental_data",
    "corporate_actions",
    "scores",
    "foreign_flow",
    "dividends",
    "macro_data",
    "technical_indicators",
    "pattern_analysis",
    "broker_flow",
    "fear_greed",
    "esg_scores",
    "corporate_governance",
    "external_events",
    "policy_events",
    "stock_personality",
    "sector_master",
    "market_calendar",
    "relationship_matrix",
    "news",
    "watchlist",
    "source_health",
    "audit_log",
    "ai_scores_historical",
    "alerts_historical",
    "backtest_results",
    "corporate_governance",
    "render_log",
]


def main():
    archive_dir = DATA_ARCHIVE_DIR / "tables"
    archive_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))

    # Get all actual tables in DB
    actual_tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'alembic_%'"
    ).fetchall()}

    print("=" * 70)
    print(f"EXPORT: SQLite -> Parquet")
    print(f"DB:      {DB_PATH}")
    print(f"Archive: {archive_dir}")
    print("=" * 70)

    exported = 0
    skipped = 0
    errors = 0

    for table in EXPORT_TABLES:
        if table not in actual_tables:
            print(f"  {table:30s} [SKIP] table not in DB")
            skipped += 1
            continue

        try:
            df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
            if df.empty:
                print(f"  {table:30s} [SKIP] empty")
                skipped += 1
                continue

            out_file = archive_dir / f"{table}.parquet"
            df.to_parquet(out_file, index=False, compression="snappy")
            exported += 1
            print(f"  {table:30s} {len(df):>10,} rows -> {out_file.name}")
        except Exception as e:
            errors += 1
            print(f"  {table:30s} ERROR: {e}")

    conn.close()

    print(f"\n{'=' * 70}")
    print(f"Export complete: {exported} exported, {skipped} skipped, {errors} errors")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
