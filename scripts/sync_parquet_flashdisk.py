"""Sync SQLite ↔ Parquet flashdisk.

Fase 1: Backup semua tabel SQLite ke Parquet di flashdisk.
Fase 2: Import Parquet lama (dari sistem pasar_modal) ke SQLite trading-system.

Penggunaan:
    python3 scripts/sync_parquet_flashdisk.py --backup      # SQLite → Parquet
    python3 scripts/sync_parquet_flashdisk.py --import      # Parquet lama → SQLite
    python3 scripts/sync_parquet_flashdisk.py --all         # Keduanya
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "trading_system.db"
PARQUET_BASE = Path(os.getenv("DATA_RAW_DIR", r"E:\trading_data\raw"))
BACKUP_DIR = PARQUET_BASE / "sqlite_backup"


def get_all_tables(conn: sqlite3.Connection) -> list[str]:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [r[0] for r in cur.fetchall()]


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]


# ═══════════════════════════════════════════════════════════════════════
# FASE 1: Backup SQLite → Parquet
# ═══════════════════════════════════════════════════════════════════════
def backup_sqlite_to_parquet():
    """Export semua tabel SQLite ke Parquet di flashdisk."""
    print("=" * 60)
    print("FASE 1: Backup SQLite → Parquet (flashdisk)")
    print("=" * 60)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))
    tables = get_all_tables(conn)

    total_rows = 0
    total_files = 0

    for table in tables:
        try:
            df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
            # Convert datetime columns to string for Parquet compatibility
            for c in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[c]):
                    df[c] = df[c].astype(str)
            out_file = BACKUP_DIR / f"{table}.parquet"
            df.to_parquet(out_file, index=False, compression="snappy")
            total_rows += len(df)
            total_files += 1
            print(f"  [OK] {table:40s} {len(df):>10,} rows → {out_file.name}")
        except Exception as e:
            print(f"  [FAIL] {table:40s} {e}")

    conn.close()
    print(f"\n  Total: {total_files} tables, {total_rows:,} rows exported")
    print(f"  Location: {BACKUP_DIR}")


# ═══════════════════════════════════════════════════════════════════════
# FASE 2: Import Parquet lama → SQLite
# ═══════════════════════════════════════════════════════════════════════

# Mapping: Parquet folder → (SQLite table, column mapping, create SQL)
# Hanya untuk data yang TIDAK ada atau lebih lengkap di Parquet

IMPORT_MAPPING = {
    "broker_flow": {
        "table": "broker_flow",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS broker_flow (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal TEXT,
                kode TEXT,
                foreign_buy REAL,
                foreign_sell REAL,
                foreign_net REAL,
                domestic_buy REAL,
                domestic_sell REAL,
                domestic_net REAL,
                total_volume REAL,
                total_value REAL
            )
        """,
        "col_map": {
            "tanggal": "tanggal",
            "kode": "kode",
            "foreign_buy": "foreign_buy",
            "foreign_sell": "foreign_sell",
            "foreign_net": "foreign_net",
            "domestic_buy": "domestic_buy",
            "domestic_sell": "domestic_sell",
            "domestic_net": "domestic_net",
            "total_volume": "total_volume",
            "total_value": "total_value",
        },
    },
    "chart_patterns": {
        "table": "chart_patterns",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS chart_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal TEXT,
                kode TEXT,
                pattern TEXT,
                pattern_type TEXT,
                confidence REAL,
                timeframe TEXT,
                created_at TEXT
            )
        """,
        "col_map": {
            "tanggal": "tanggal",
            "kode": "kode",
            "pattern": "pattern",
            "pattern_type": "pattern_type",
            "confidence": "confidence",
            "timeframe": "timeframe",
            "created_at": "created_at",
        },
    },
    "commodity": {
        "table": "commodity_data",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS commodity_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal TEXT,
                nama TEXT,
                satuan TEXT,
                nilai REAL,
                perubahan REAL,
                created_at TEXT
            )
        """,
        "col_map": {
            "tanggal": "tanggal",
            "nama": "nama",
            "satuan": "satuan",
            "nilai": "nilai",
            "perubahan": "perubahan",
            "created_at": "created_at",
        },
    },
    "global": {
        "table": "global_market_data",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS global_market_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal TEXT,
                nama TEXT,
                negara TEXT,
                nilai REAL,
                perubahan REAL,
                created_at TEXT
            )
        """,
        "col_map": {
            "tanggal": "tanggal",
            "nama": "nama",
            "negara": "negara",
            "nilai": "nilai",
            "perubahan": "perubahan",
            "created_at": "created_at",
        },
    },
    "ihsg": {
        "table": "ihsg_data",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS ihsg_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal TEXT,
                harga REAL,
                perubahan REAL,
                volume REAL,
                created_at TEXT
            )
        """,
        "col_map": {
            "tanggal": "tanggal",
            "harga": "harga",
            "perubahan": "perubahan",
            "volume": "volume",
            "created_at": "created_at",
        },
    },
    "multi_asset": {
        "table": "multi_asset_data",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS multi_asset_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kode TEXT,
                nama TEXT,
                jenis TEXT,
                harga REAL,
                change_pct REAL,
                tanggal TEXT
            )
        """,
        "col_map": {
            "kode": "kode",
            "nama": "nama",
            "jenis": "jenis",
            "harga": "harga",
            "change_pct": "change_pct",
            "tanggal": "tanggal",
        },
    },
    "stock_ipo": {
        "table": "stock_ipo",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS stock_ipo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kode TEXT,
                ipo_date TEXT,
                ipo_price REAL,
                shares_offered REAL,
                underwriter TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """,
        "col_map": {
            "kode": "kode",
            "ipo_date": "ipo_date",
            "ipo_price": "ipo_price",
            "shares_offered": "shares_offered",
            "underwriter": "underwriter",
            "created_at": "created_at",
            "updated_at": "updated_at",
        },
    },
    "saham_historical": {
        "table": "saham_historical",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS saham_historical (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kode TEXT,
                tanggal TEXT,
                harga_close REAL,
                harga_open REAL,
                harga_high REAL,
                harga_low REAL,
                volume REAL
            )
        """,
        "col_map": {
            "kode": "kode",
            "tanggal": "tanggal",
            "harga_close": "harga_close",
            "harga_open": "harga_open",
            "harga_high": "harga_high",
            "harga_low": "harga_low",
            "volume": "volume",
        },
    },
    "data_fetch_log": {
        "table": "data_fetch_log",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS data_fetch_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kode TEXT,
                fetch_type TEXT,
                start_date TEXT,
                end_date TEXT,
                records_fetched INTEGER,
                records_inserted INTEGER,
                records_updated INTEGER
            )
        """,
        "col_map": {
            "kode": "kode",
            "fetch_type": "fetch_type",
            "start_date": "start_date",
            "end_date": "end_date",
            "records_fetched": "records_fetched",
            "records_inserted": "records_inserted",
            "records_updated": "records_updated",
        },
    },
    "notifications": {
        "table": "notifications",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipe TEXT,
                kode TEXT,
                judul TEXT,
                pesan TEXT,
                level TEXT,
                is_read INTEGER,
                created_at TEXT
            )
        """,
        "col_map": {
            "tipe": "tipe",
            "kode": "kode",
            "judul": "judul",
            "pesan": "pesan",
            "level": "level",
            "is_read": "is_read",
            "created_at": "created_at",
        },
    },
    "price_alerts": {
        "table": "price_alerts",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS price_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trader_id TEXT,
                kode TEXT,
                alert_type TEXT,
                target_value REAL,
                current_value REAL,
                status TEXT,
                triggered_at TEXT
            )
        """,
        "col_map": {
            "trader_id": "trader_id",
            "kode": "kode",
            "alert_type": "alert_type",
            "target_value": "target_value",
            "current_value": "current_value",
            "status": "status",
            "triggered_at": "triggered_at",
        },
    },
    "strategy_config": {
        "table": "strategy_config",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS strategy_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                description TEXT,
                config_json TEXT,
                target_type TEXT,
                target_code TEXT,
                period_days INTEGER,
                stop_loss_pct REAL
            )
        """,
        "col_map": {
            "name": "name",
            "description": "description",
            "config_json": "config_json",
            "target_type": "target_type",
            "target_code": "target_code",
            "period_days": "period_days",
            "stop_loss_pct": "stop_loss_pct",
        },
    },
    "trade_journal": {
        "table": "trade_journal_imported",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS trade_journal_imported (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trader_id TEXT,
                kode TEXT,
                jenis TEXT,
                tanggal TEXT,
                harga REAL,
                jumlah REAL,
                alasan TEXT
            )
        """,
        "col_map": {
            "trader_id": "trader_id",
            "kode": "kode",
            "jenis": "jenis",
            "tanggal": "tanggal",
            "harga": "harga",
            "jumlah": "jumlah",
            "alasan": "alasan",
        },
    },
    "training_log": {
        "table": "ml_training_log",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS ml_training_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mode TEXT,
                stocks TEXT,
                lookback INTEGER,
                forecast_horizon INTEGER,
                status TEXT,
                started_at TEXT,
                completed_at TEXT
            )
        """,
        "col_map": {
            "mode": "mode",
            "stocks": "stocks",
            "lookback": "lookback",
            "forecast_horizon": "forecast_horizon",
            "status": "status",
            "started_at": "started_at",
            "completed_at": "completed_at",
        },
    },
    "ml_config": {
        "table": "ml_config",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS ml_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_key TEXT UNIQUE,
                config_value TEXT,
                description TEXT,
                updated_at TEXT
            )
        """,
        "col_map": {
            "config_key": "config_key",
            "config_value": "config_value",
            "description": "description",
            "updated_at": "updated_at",
        },
    },
    "trader_saldo": {
        "table": "trader_saldo",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS trader_saldo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trader_id TEXT,
                saldo REAL,
                created_at TEXT
            )
        """,
        "col_map": {
            "trader_id": "trader_id",
            "saldo": "saldo",
            "created_at": "created_at",
        },
    },
    "backtest_result": {
        "table": "backtest_result_imported",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS backtest_result_imported (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date TEXT,
                strategy TEXT,
                total_return REAL,
                benchmark_return REAL,
                alpha REAL,
                sharpe_ratio REAL,
                max_drawdown REAL
            )
        """,
        "col_map": {
            "run_date": "run_date",
            "strategy": "strategy",
            "total_return": "total_return",
            "benchmark_return": "benchmark_return",
            "alpha": "alpha",
            "sharpe_ratio": "sharpe_ratio",
            "max_drawdown": "max_drawdown",
        },
    },
    "blind_forecast": {
        "table": "blind_forecast",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS blind_forecast (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kode TEXT,
                trader_id TEXT,
                direction TEXT,
                predicted_price REAL,
                current_price REAL,
                target_pct REAL,
                timeframe TEXT
            )
        """,
        "col_map": {
            "kode": "kode",
            "trader_id": "trader_id",
            "direction": "direction",
            "predicted_price": "predicted_price",
            "current_price": "current_price",
            "target_pct": "target_pct",
            "timeframe": "timeframe",
        },
    },
    "ai_alerts": {
        "table": "ai_alerts",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS ai_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal TEXT,
                kode TEXT,
                alert_type TEXT,
                severity TEXT,
                message TEXT,
                created_at TEXT
            )
        """,
        "col_map": {},
    },
    "ai_auto_trade": {
        "table": "ai_auto_trade",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS ai_auto_trade (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal TEXT,
                kode TEXT,
                action TEXT,
                shares REAL,
                price REAL,
                status TEXT,
                created_at TEXT
            )
        """,
        "col_map": {},
    },
    "ai_portfolio": {
        "table": "ai_portfolio",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS ai_portfolio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal TEXT,
                kode TEXT,
                alokasi_pct REAL,
                target_value REAL,
                risk_level TEXT,
                created_at TEXT
            )
        """,
        "col_map": {},
    },
    "ai_correlation": {
        "table": "ai_correlation",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS ai_correlation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal TEXT,
                kode_a TEXT,
                kode_b TEXT,
                correlation REAL,
                lag INTEGER,
                created_at TEXT
            )
        """,
        "col_map": {},
    },
    # Master data IDX (mm_*)
    "mm_instrument": {
        "table": "mm_instrument",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS mm_instrument (
                instrument_id TEXT PRIMARY KEY,
                security_id TEXT,
                asset_class TEXT,
                instrument_type TEXT,
                currency TEXT,
                status TEXT,
                status_changed_at TEXT
            )
        """,
        "col_map": {},
    },
    "mm_security": {
        "table": "mm_security",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS mm_security (
                security_id TEXT PRIMARY KEY,
                issuer_id TEXT,
                security_type TEXT,
                currency TEXT,
                issue_date TEXT,
                maturity_date TEXT,
                par_value REAL,
                status TEXT
            )
        """,
        "col_map": {},
    },
    "mm_issuer": {
        "table": "mm_issuer",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS mm_issuer (
                issuer_id TEXT PRIMARY KEY,
                legal_name TEXT,
                short_name TEXT,
                country TEXT,
                jurisdiction TEXT,
                legal_entity_identifier TEXT,
                status TEXT,
                incorporation_date TEXT
            )
        """,
        "col_map": {},
    },
    "mm_listing": {
        "table": "mm_listing",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS mm_listing (
                listing_id TEXT PRIMARY KEY,
                instrument_id TEXT,
                exchange_id TEXT,
                ticker TEXT,
                isin TEXT,
                currency TEXT,
                listing_date TEXT,
                delisting_date TEXT
            )
        """,
        "col_map": {},
    },
    "mm_exchange": {
        "table": "mm_exchange",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS mm_exchange (
                exchange_id TEXT PRIMARY KEY,
                name TEXT,
                mic_code TEXT,
                country TEXT,
                timezone TEXT,
                currency TEXT,
                status TEXT
            )
        """,
        "col_map": {},
    },
    # SQLite exports dari sistem lama
    "sqlite_global_market_data": {
        "table": "legacy_global_market_data",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS legacy_global_market_data (
                date TEXT,
                ticker TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                adj_close REAL,
                volume REAL
            )
        """,
        "col_map": {},
    },
    "sqlite_instruments": {
        "table": "legacy_instruments",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS legacy_instruments (
                ticker TEXT,
                name TEXT,
                instrument_type TEXT,
                exchange TEXT,
                sector TEXT,
                industry TEXT,
                currency TEXT,
                board TEXT
            )
        """,
        "col_map": {},
    },
    "sqlite_macro_data": {
        "table": "legacy_macro_data",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS legacy_macro_data (
                date TEXT,
                series_id TEXT,
                value REAL,
                region TEXT,
                category TEXT,
                data_source TEXT,
                created_at TEXT
            )
        """,
        "col_map": {},
    },
    "sqlite_ohlcv": {
        "table": "legacy_ohlcv",
        "create_sql": """
            CREATE TABLE IF NOT EXISTS legacy_ohlcv (
                date TEXT,
                ticker TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                adj_close REAL,
                volume REAL
            )
        """,
        "col_map": {},
    },
}


def import_parquet_to_sqlite():
    """Import Parquet lama (dari sistem pasar_modal) ke SQLite trading-system."""
    print("=" * 60)
    print("FASE 2: Import Parquet lama → SQLite")
    print("=" * 60)

    conn = sqlite3.connect(str(DB_PATH))
    total_imported = 0
    total_tables = 0

    for parquet_folder, config in IMPORT_MAPPING.items():
        folder_path = PARQUET_BASE / parquet_folder
        if not folder_path.exists():
            print(f"  [SKIP] {parquet_folder:40s} folder not found")
            continue

        files = sorted(folder_path.glob("*.parquet"))
        if not files:
            print(f"  [SKIP] {parquet_folder:40s} no parquet files")
            continue

        table = config["table"]
        create_sql = config["create_sql"]
        col_map = config["col_map"]

        # Create table
        conn.execute(create_sql)
        conn.commit()

        # Check existing rows
        try:
            cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
            existing = cur.fetchone()[0]
        except Exception:
            existing = 0

        # Read all parquet files
        dfs = []
        for f in files:
            try:
                df = pd.read_parquet(f)
                dfs.append(df)
            except Exception as e:
                print(f"  [WARN] {parquet_folder:40s} cannot read {f.name}: {e}")

        if not dfs:
            print(f"  [SKIP] {parquet_folder:40s} no readable files")
            continue

        df = pd.concat(dfs, ignore_index=True)

        # Drop 'id' column if present (let SQLite auto-increment)
        if "id" in df.columns:
            df = df.drop(columns=["id"])

        # Convert Timestamp/datetime columns to string for SQLite compatibility
        for c in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[c]):
                df[c] = df[c].astype(str)
            elif df[c].dtype == object:
                # Check if contains Timestamp objects
                if len(df) > 0 and hasattr(df[c].iloc[0], "strftime"):
                    df[c] = df[c].astype(str)

        # Apply column mapping if specified
        if col_map:
            rename = {k: v for k, v in col_map.items() if k in df.columns}
            if rename:
                df = df.rename(columns=rename)

        # Only keep columns that exist in the SQLite table
        db_cols = table_columns(conn, table)
        df = df[[c for c in df.columns if c in db_cols]]

        if df.empty:
            print(f"  [SKIP] {parquet_folder:40s} no matching columns")
            continue

        # Insert with INSERT OR IGNORE to avoid duplicates
        placeholders = ",".join(["?" for _ in df.columns])
        col_names = ",".join(df.columns)
        rows = [tuple(x) for x in df.itertuples(index=False, name=None)]

        try:
            conn.executemany(
                f"INSERT OR IGNORE INTO {table} ({col_names}) VALUES ({placeholders})",
                rows,
            )
            conn.commit()
            inserted = len(rows)
            total_imported += inserted
            total_tables += 1
            print(f"  [OK]   {parquet_folder:40s} → {table:40s} {inserted:>10,} rows (was {existing:,})")
        except Exception as e:
            print(f"  [FAIL] {parquet_folder:40s} → {table:40s} {e}")
            conn.rollback()

    conn.close()
    print(f"\n  Total: {total_tables} tables imported, {total_imported:,} rows")


# ═══════════════════════════════════════════════════════════════════════
# FASE 3: Verifikasi
# ═══════════════════════════════════════════════════════════════════════
def verify():
    """Bandingkan row counts SQLite vs Parquet."""
    print("=" * 60)
    print("FASE 3: Verifikasi")
    print("=" * 60)

    conn = sqlite3.connect(str(DB_PATH))
    tables = get_all_tables(conn)

    print(f"\n  {'Table':45s} {'SQLite':>12s} {'Parquet':>12s}")
    print(f"  {'-' * 45} {'-' * 12} {'-' * 12}")

    for table in tables:
        cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
        sqlite_count = cur.fetchone()[0]

        # Check backup parquet
        backup_file = BACKUP_DIR / f"{table}.parquet"
        parquet_count = "N/A"
        if backup_file.exists():
            try:
                df = pd.read_parquet(backup_file, columns=None)
                parquet_count = f"{len(df):,}"
            except Exception:
                parquet_count = "ERR"

        print(f"  {table:45s} {sqlite_count:>12,} {parquet_count:>12s}")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Sync SQLite ↔ Parquet flashdisk")
    parser.add_argument("--backup", action="store_true", help="Backup SQLite → Parquet")
    parser.add_argument("--import", dest="do_import", action="store_true", help="Import Parquet lama → SQLite")
    parser.add_argument("--all", action="store_true", help="Lakukan keduanya + verifikasi")
    parser.add_argument("--verify", action="store_true", help="Hanya verifikasi")
    args = parser.parse_args()

    if args.all:
        backup_sqlite_to_parquet()
        print()
        import_parquet_to_sqlite()
        print()
        verify()
    elif args.backup:
        backup_sqlite_to_parquet()
    elif args.do_import:
        import_parquet_to_sqlite()
    elif args.verify:
        verify()
    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
