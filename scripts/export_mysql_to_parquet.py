"""Export data dari MySQL (data_pasar_modal) ke Parquet di archive directory.

Penggunaan:
    python -m scripts.export_mysql_to_parquet --archive-dir "K:\\trading_data\\raw"
    python -m scripts.export_mysql_to_parquet --tables ohlcv broker_flow --archive-dir "K:\\trading_data\\raw"

Data disimpan sebagai Parquet terkompresi (snappy) per tabel, dipartisi
per tahun untuk tabel besar (stock_history).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
import pymysql


def get_connection():
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", "root"),
        database="data_pasar_modal",
        charset="utf8mb4",
    )


TABLE_MAP = {
    "ohlcv": {
        "mysql_table": "stock_history",
        "partition_by": "year",
        "date_col": "tanggal",
    },
    "broker_flow": {
        "mysql_table": "broker_flow",
        "partition_by": None,
        "date_col": None,
    },
    "sentiment": {
        "mysql_table": "berita_sentimen",
        "partition_by": None,
        "date_col": None,
    },
    "macro": {
        "mysql_table": "makroekonomi",
        "partition_by": None,
        "date_col": None,
    },
    "fundamental": {
        "mysql_table": "saham_fundamental",
        "partition_by": None,
        "date_col": None,
    },
    "global": {
        "mysql_table": "bursa_global",
        "partition_by": None,
        "date_col": None,
    },
    "technical": {
        "mysql_table": "saham_teknikal",
        "partition_by": None,
        "date_col": None,
    },
    "ihsg": {
        "mysql_table": "ihsg_history",
        "partition_by": None,
        "date_col": None,
    },
    "commodity": {
        "mysql_table": "komoditas",
        "partition_by": None,
        "date_col": None,
    },
    "corporate_action": {
        "mysql_table": "aksi_korporasi",
        "partition_by": None,
        "date_col": None,
    },
}


def export_table(conn, name: str, config: dict, archive_dir: Path, batch_size: int = 50000):
    mysql_table = config["mysql_table"]
    partition_by = config.get("partition_by")
    date_col = config.get("date_col")

    out_dir = archive_dir / name
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"Exporting: {mysql_table} -> {name}/")

    # Check if table exists
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema='data_pasar_modal' AND table_name=%s",
            (mysql_table,),
        )
        if cur.fetchone()[0] == 0:
            print(f"  SKIP: Table {mysql_table} not found")
            return 0

        cur.execute(f"SELECT COUNT(*) FROM `{mysql_table}`")
        total_rows = cur.fetchone()[0]
    print(f"  Total rows: {total_rows:,}")

    if total_rows == 0:
        print(f"  SKIP: Empty table")
        return 0

    if partition_by == "year" and date_col:
        # Partitioned export by year
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT DISTINCT YEAR(`{date_col}`) FROM `{mysql_table}` "
                f"WHERE `{date_col}` IS NOT NULL ORDER BY 1"
            )
            years = [r[0] for r in cur.fetchall()]

        total_exported = 0
        for year in years:
            offset = 0
            year_dfs = []
            while True:
                query = (
                    f"SELECT * FROM `{mysql_table}` "
                    f"WHERE YEAR(`{date_col}`) = {year} "
                    f"LIMIT {batch_size} OFFSET {offset}"
                )
                batch = pd.read_sql(query, conn)
                if batch.empty:
                    break
                year_dfs.append(batch)
                offset += batch_size
                if offset >= total_rows:
                    break

            if year_dfs:
                year_df = pd.concat(year_dfs, ignore_index=True)
                out_file = out_dir / f"{name}_{year}.parquet"
                year_df.to_parquet(out_file, index=False, compression="snappy")
                size_kb = out_file.stat().st_size / 1024
                print(f"  {year}: {len(year_df):,} rows -> {out_file.name} ({size_kb:.0f} KB)")
                total_exported += len(year_df)

        return total_exported
    else:
        # Single file export
        df = pd.read_sql(f"SELECT * FROM `{mysql_table}`", conn)
        out_file = out_dir / f"{name}.parquet"
        df.to_parquet(out_file, index=False, compression="snappy")
        size_kb = out_file.stat().st_size / 1024
        print(f"  {len(df):,} rows -> {out_file.name} ({size_kb:.0f} KB)")
        return len(df)


def main():
    parser = argparse.ArgumentParser(description="Export MySQL data_pasar_modal to Parquet archive")
    parser.add_argument(
        "--archive-dir",
        default=os.getenv("DATA_ARCHIVE_DIR", "K:\\trading_data\\raw"),
        help="Archive directory path (default: K:\\trading_data\\raw or DATA_ARCHIVE_DIR env)",
    )
    parser.add_argument(
        "--tables",
        nargs="*",
        default=None,
        help=f"Tables to export (default: all). Available: {', '.join(TABLE_MAP.keys())}",
    )
    args = parser.parse_args()

    archive_dir = Path(args.archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)
    print(f"Archive directory: {archive_dir}")

    tables = args.tables or list(TABLE_MAP.keys())
    conn = get_connection()

    total = 0
    for name in tables:
        if name not in TABLE_MAP:
            print(f"  WARNING: Unknown table '{name}', skipping")
            continue
        try:
            exported = export_table(conn, name, TABLE_MAP[name], archive_dir)
            total += exported
        except Exception as e:
            print(f"  ERROR exporting {name}: {e}")

    conn.close()
    print(f"\n{'='*60}")
    print(f"Total rows exported: {total:,}")
    print(f"Archive location: {archive_dir}")


if __name__ == "__main__":
    main()
