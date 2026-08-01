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
from datetime import datetime
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
        "column_mapping": {
            "periode": "date",
            # Note: macro data needs unpivoting - handled separately
        },
        "unpivot": True,  # Special flag for macro data
    },
    "saham": {
        "sqlite_table": "instrument_master",
        "column_mapping": {
            "kode": "ticker",
            "nama": "name",
            "sektor": "sector",
            "ipo_date": "listing_date",
            "delisted_date": "delisting_date",
            "status": "is_active",
            "market_cap": "market_cap",
            "created_at": "updated_at",
        },
        "add_suffix": True,  # Add .JK to ticker
    },
    "fundamental": {
        "sqlite_table": "fundamental_data",
        "column_mapping": {
            "kode": "ticker",
            "periode": "date",
            "eps": "earnings_per_share",
            "book_value_per_share": "book_value_per_share",
            "net_profit": "net_profit",
            "revenue": "revenue",
            "created_at": None,  # Don't import
        },
        "add_suffix": True,
        "add_source": "parquet_import",
    },
    "foreign_flow": {
        "sqlite_table": "foreign_flow",
        "column_mapping": {
            "tanggal": "date",
            "beli": "foreign_buy",
            "jual": "foreign_sell",
            "net": "foreign_net",
            "created_at": None,
        },
        "add_ticker": "^JKSE",  # Add default ticker for aggregate data
        "add_source": "parquet_import",
    },
    "broker_flow": {
        "sqlite_table": "broker_flow",
        "column_mapping": {
            "tanggal": "date",
            "kode": "ticker",
            "foreign_buy": "buy_volume",
            "foreign_sell": "sell_volume",
            "foreign_net": "net_volume",
            "domestic_buy": "buy_value",
            "domestic_sell": "sell_value",
            "domestic_net": "net_value",
            "created_at": None,
        },
        "add_suffix": True,
        "add_source": "parquet_import",
    },
    "kebijakan_regulasi": {
        "sqlite_table": "policy_events",
        "column_mapping": {
            "tanggal": "date",
            "jenis": "event_type",
            "deskripsi": "description",
            "dampak": "impact",
            "created_at": None,
        },
        "add_source": "parquet_import",
    },
    "corporate_action": {
        "sqlite_table": "corporate_actions_legacy",
        "column_mapping": {
            "tanggal": "ex_date",
            "kode": "ticker",
            "jenis": "action_type",
            "nilai": "value",
            "created_at": None,
        },
        "add_suffix": True,
    },
    "sektor": {
        "sqlite_table": "sector_master",
        "column_mapping": {
            "kode": "sector_code",
            "nama": "sector_name",
            "created_at": "updated_at",
        },
    },
    "fear_greed_index": {
        "sqlite_table": "fear_greed",
        "column_mapping": {
            "tanggal": "date",
            "nilai": "value",
            "label": "classification",
            "created_at": "updated_at",
        },
        "add_source": "parquet_import",
    },
    "event_eksternal": {
        "sqlite_table": "external_events",
        "column_mapping": {
            "tanggal": "date",
            "tipe": "event_type",
            "deskripsi": "description",
            "dampak": "impact_level",
            "created_at": None,
        },
        "add_source": "parquet_import",
    },
    "esg_scores": {
        "sqlite_table": "esg_scores",
        "column_mapping": {
            "kode": "ticker",
            "tanggal": "date",
            "environment_score": "e_score",
            "social_score": "s_score",
            "governance_score": "g_score",
            "total_score": "esg_score",
            "created_at": None,
        },
        "add_suffix": True,
        "add_source": "parquet_import",
    },
    "corporate_governance": {
        "sqlite_table": "corporate_governance",
        "column_mapping": {
            "kode": "ticker",
            "tanggal": "date",
            "created_at": None,
        },
        "add_suffix": True,
        "add_source": "parquet_import",
    },
    "stock_personality": {
        "sqlite_table": "stock_personality",
        "column_mapping": {
            "kode": "ticker",
            "personality_label": "personality_type",
            "volatility_regime": "volatility_profile",
            "liquidity_score": "liquidity_profile",
            "beta_vs_ihsg": "beta",
            "created_at": "updated_at",
        },
        "add_suffix": True,
    },
    # Skip backtest_result - table doesn't exist in schema
    # "backtest_result": {
    #     "sqlite_table": "backtest_results",
    #     "column_mapping": {
    #         "created_at": None,
    #     },
    # },
    "trade_journal": {
        "sqlite_table": "trade_journal",
        "column_mapping": {
            "kode": "ticker",
            "created_at": None,
        },
        "add_suffix": True,
    },
    "pattern_analysis": {
        "sqlite_table": "pattern_analysis",
        "column_mapping": {
            "kode": "ticker",
            "tanggal": "date",
            "created_at": None,
        },
        "add_suffix": True,
    },
    "indikator_teknikal": {
        "sqlite_table": "technical_indicators",
        "column_mapping": {
            "kode": "ticker",
            "tanggal": "date",
            "created_at": None,
        },
        "add_suffix": True,
        "add_source": "parquet_import",
    },
}

# Tables that have UNIQUE constraints — use INSERT OR REPLACE
UNIQUE_TABLES = {
    "instrument_master",  # ticker UNIQUE
    "sector_master",  # sector_code UNIQUE
    "fear_greed",  # date UNIQUE
    "fundamental_data",  # UNIQUE(ticker, date, source)
    "esg_scores",  # UNIQUE(ticker, date, source)
    "corporate_governance",  # UNIQUE(ticker, date, source)
    "technical_indicators",  # UNIQUE(ticker, date, indicator, timeframe, source)
    "stock_personality",  # ticker UNIQUE
}

# Tables with autoincrement IDs - drop id column before import
AUTOINCREMENT_TABLES = {
    "external_events", "policy_events", 
    "backtest_results", "pattern_analysis", "trade_journal"
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
    mapping_config = TABLE_MAPPING.get(parquet_name, {})
    df = load_parquet_table(parquet_dir, parquet_name)
    if df.empty:
        return {"status": "empty", "table": parquet_name, "rows": 0}

    # Convert dates to strings
    df = convert_dates(df)

    # Apply column mapping
    column_mapping = mapping_config.get("column_mapping", {})
    if column_mapping:
        # Rename columns according to mapping
        rename_dict = {k: v for k, v in column_mapping.items() if v is not None}
        df = df.rename(columns=rename_dict)
        
        # Drop columns that map to None (don't import)
        drop_cols = [k for k, v in column_mapping.items() if v is None]
        df = df.drop(columns=[c for c in drop_cols if c in df.columns], errors='ignore')

    # Add .JK suffix to ticker if needed
    if mapping_config.get("add_suffix"):
        if "ticker" in df.columns:
            df["ticker"] = df["ticker"].apply(lambda x: f"{x}.JK" if x and not x.endswith(".JK") else x)

    # Add default ticker if needed
    if mapping_config.get("add_ticker"):
        default_ticker = mapping_config["add_ticker"]
        if "ticker" not in df.columns:
            df["ticker"] = default_ticker

    # Add source column if needed
    if mapping_config.get("add_source"):
        source = mapping_config["add_source"]
        if "source" not in df.columns:
            df["source"] = source
    
    # Add created_at if needed for tables that require it
    if sqlite_table in AUTOINCREMENT_TABLES:
        if "created_at" not in df.columns:
            df["created_at"] = datetime.now().isoformat()
        # Drop id column for autoincrement tables to avoid conflicts
        if "id" in df.columns:
            df = df.drop(columns=["id"])

    # Handle is_active conversion
    if "is_active" in df.columns:
        df["is_active"] = df["is_active"].apply(lambda x: 1 if str(x).upper() == "ACTIVE" else 0)

    # Handle macro data unpivoting
    if mapping_config.get("unpivot"):
        # Macro data needs special handling - unpivot wide format to long format
        id_vars = ["date"]
        value_vars = ["suku_bunga", "inflasi", "gdp_growth", "kurs_usd"]
        
        # Rename date column first
        if "periode" in df.columns:
            df = df.rename(columns={"periode": "date"})
        
        # Unpivot
        df_melted = df.melt(
            id_vars=id_vars,
            value_vars=value_vars,
            var_name="series_name",
            value_name="value"
        )
        
        # Map series names to standard names
        series_mapping = {
            "suku_bunga": "BI_RATE",
            "inflasi": "INFLATION",
            "gdp_growth": "GDP_GROWTH",
            "kurs_usd": "USD_IDR"
        }
        df_melted["series_name"] = df_melted["series_name"].map(series_mapping)
        
        # Add other required columns
        df_melted["unit"] = df_melted["series_name"].apply(lambda x: "%" if x in ["BI_RATE", "INFLATION", "GDP_GROWTH"] else "IDR")
        df_melted["source"] = "parquet_import"
        df_melted["frequency"] = "monthly"
        
        df = df_melted

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
            # For unique tables, filter out existing rows to avoid conflicts
            # Get existing unique keys
            if sqlite_table == "fear_greed" and "date" in df.columns:
                existing = conn.execute(f"SELECT date FROM {sqlite_table}").fetchall()
                existing_dates = {row[0] for row in existing}
                df = df[~df["date"].isin(existing_dates)]
            elif sqlite_table == "instrument_master" and "ticker" in df.columns:
                existing = conn.execute(f"SELECT ticker FROM {sqlite_table}").fetchall()
                existing_tickers = {row[0] for row in existing}
                df = df[~df["ticker"].isin(existing_tickers)]
            elif sqlite_table == "sector_master" and "sector_code" in df.columns:
                existing = conn.execute(f"SELECT sector_code FROM {sqlite_table}").fetchall()
                existing_sectors = {row[0] for row in existing}
                df = df[~df["sector_code"].isin(existing_sectors)]
            elif sqlite_table == "stock_personality" and "ticker" in df.columns:
                existing = conn.execute(f"SELECT ticker FROM {sqlite_table}").fetchall()
                existing_tickers = {row[0] for row in existing}
                df = df[~df["ticker"].isin(existing_tickers)]
            
            # If no rows left after filtering, skip
            if len(df) == 0:
                return {
                    "status": "skipped",
                    "table": parquet_name,
                    "sqlite_table": sqlite_table,
                    "rows": 0,
                    "reason": "all rows already exist",
                }
        
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

        mapping_config = TABLE_MAPPING[parquet_name]
        sqlite_table = mapping_config["sqlite_table"]
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
