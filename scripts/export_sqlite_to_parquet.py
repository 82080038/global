"""Export SQLite saham.db (pasar_modal) to Parquet archive.

Usage:
    python -m scripts.export_sqlite_to_parquet --archive-dir "K:\\trading_data\\raw"
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd


def export_sqlite(db_path: str, archive_dir: Path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]

    total = 0
    for table in tables:
        if table in ("sqlite_sequence", "alembic_version"):
            continue
        try:
            df = pd.read_sql(f"SELECT * FROM [{table}]", conn)
        except Exception as e:
            print(f"  ERROR reading {table}: {e}")
            continue

        if df.empty:
            print(f"  SKIP {table}: empty")
            continue

        out_dir = archive_dir / f"sqlite_{table}"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"sqlite_{table}.parquet"
        df.to_parquet(out_file, index=False, compression="snappy")
        size_kb = out_file.stat().st_size / 1024
        print(f"  {table}: {len(df):,} rows -> {out_file.name} ({size_kb:.0f} KB)")
        total += len(df)

    conn.close()
    return total


def main():
    parser = argparse.ArgumentParser(description="Export SQLite saham.db to Parquet")
    parser.add_argument(
        "--db-path",
        default=r"C:\xampp\htdocs\pasar_modal\data\saham.db",
        help="Path to saham.db",
    )
    parser.add_argument(
        "--archive-dir",
        default=r"K:\trading_data\raw",
        help="Archive directory",
    )
    args = parser.parse_args()

    archive_dir = Path(args.archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)
    print(f"DB: {args.db_path}")
    print(f"Archive: {archive_dir}")

    total = export_sqlite(args.db_path, archive_dir)
    print(f"\nTotal rows exported: {total:,}")


if __name__ == "__main__":
    main()
