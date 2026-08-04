"""Import data from legacy sources (saham.db, MySQL exports) to global SQLite DB.

Implements §13.5 #5 — Import Parquet/MySQL → SQLite (§11.4b).
Uses mapping from docs/MAPPING_PARQUET_SQLITE.md.
"""
import sqlite3
from datetime import UTC, datetime

import pandas as pd

from trading_system.data.storage import DataStorage
from trading_system.data.validation import DataQualityValidator


class LegacyDataImporter:
    """Import data from legacy SQLite (saham.db) to global SQLite."""

    def __init__(
        self,
        source_db: str = "C:/xampp/htdocs/pasar_modal/data/saham.db",
        target_storage: DataStorage | None = None,
    ):
        self.source_db = source_db
        self.storage = target_storage or DataStorage()
        self.validator = DataQualityValidator()
        self.stats: dict[str, int] = {}

    def import_all(self) -> dict[str, int]:
        """Run all imports in priority order."""
        self._import_ohlcv()
        self._import_instruments()
        self._import_macro_data()
        self._import_global_market_data()
        self._import_dividends()
        self._import_journal_entries()
        return self.stats

    def _connect_source(self) -> sqlite3.Connection:
        return sqlite3.connect(self.source_db)

    def _log(self, table: str, n: int):
        self.stats[table] = n
        print(f"  {table}: {n} rows")

    def _import_ohlcv(self):
        """Import OHLCV data from saham.db::ohlcv → global::ohlcv."""
        print("Importing OHLCV...")
        conn = self._connect_source()
        df = pd.read_sql_query("SELECT * FROM ohlcv", conn)
        conn.close()

        if df.empty:
            self._log("ohlcv", 0)
            return

        df = df.copy()
        df.rename(columns={
            "date": "timestamp", "adj_close": "adjusted_close",
        }, inplace=True)

        if "adjusted_close" not in df.columns:
            df["adjusted_close"] = df["close"]
        df["asset_class"] = "equity"
        df["exchange"] = "IDX"
        df["timeframe"] = "1d"
        df["source"] = "saham_db"
        df["ingested_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        df["data_quality_score"] = None

        for col in ["open", "high", "low", "close", "volume", "adjusted_close"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        clean, report = self.validator.validate(df)
        if report.action == "pause":
            print(f"  ohlcv: SKIPPED (quality={report.data_quality_score}, tier={report.tier})")
            self._log("ohlcv", 0)
            return
        n = self.storage.save_ohlcv(clean)
        self._log("ohlcv", n)

    def _import_instruments(self):
        """Import from saham.db::instruments → global::instrument_master."""
        print("Importing instruments...")
        conn = self._connect_source()
        try:
            df = pd.read_sql_query("SELECT * FROM instruments", conn)
        except Exception:
            conn.close()
            self._log("instrument_master", 0)
            return
        conn.close()

        if df.empty:
            self._log("instrument_master", 0)
            return

        rows = []
        for _, r in df.iterrows():
            rows.append((
                r.get("ticker"), r.get("name"), r.get("sector"),
                r.get("industry"), r.get("exchange", "IDX"),
                None, None, int(r.get("is_active", 1)),
                r.get("board"), None, None,
                datetime.now(UTC).isoformat(),
            ))

        sql = """INSERT OR REPLACE INTO instrument_master
            (ticker, name, sector, subsector, exchange, listing_date,
             delisting_date, is_active, board, market_cap, free_float, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        n = self.storage.executemany_batch(sql, rows)
        self._log("instrument_master", n)

    def _import_macro_data(self):
        """Import from saham.db::macro_data → global::macro_data."""
        print("Importing macro_data...")
        conn = self._connect_source()
        try:
            df = pd.read_sql_query("SELECT * FROM macro_data", conn)
        except Exception:
            conn.close()
            self._log("macro_data", 0)
            return
        conn.close()

        if df.empty:
            self._log("macro_data", 0)
            return

        rows = []
        for _, r in df.iterrows():
            rows.append((
                str(r.get("series_id", "")),
                str(r.get("date", "")),
                float(r.get("value", 0) or 0),
                "", str(r.get("data_source", "saham_db")),
                str(r.get("category", "")),
            ))

        sql = """INSERT OR REPLACE INTO macro_data
            (series_name, date, value, unit, source, frequency)
            VALUES (?, ?, ?, ?, ?, ?)"""
        n = self.storage.executemany_batch(sql, rows)
        self._log("macro_data", n)

    def _import_global_market_data(self):
        """Import from saham.db::global_market_data → global::ohlcv (non-IDX)."""
        print("Importing global_market_data...")
        conn = self._connect_source()
        try:
            df = pd.read_sql_query("SELECT * FROM global_market_data", conn)
        except Exception:
            conn.close()
            self._log("global_market_data", 0)
            return
        conn.close()

        if df.empty:
            self._log("global_market_data", 0)
            return

        df = df.copy()
        df.rename(columns={
            "date": "timestamp", "adj_close": "adjusted_close",
        }, inplace=True)

        if "adjusted_close" not in df.columns:
            df["adjusted_close"] = df["close"]
        df["asset_class"] = "equity"
        df["exchange"] = "GLOBAL"
        df["timeframe"] = "1d"
        df["source"] = "saham_db_global"
        df["ingested_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        df["data_quality_score"] = None

        for col in ["open", "high", "low", "close", "volume", "adjusted_close"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        clean, report = self.validator.validate(df)
        if report.action == "pause":
            print(f"  global_market_data: SKIPPED (quality={report.data_quality_score}, tier={report.tier})")
            self._log("global_market_data", 0)
            return
        n = self.storage.save_ohlcv(clean)
        self._log("global_market_data", n)

    def _import_dividends(self):
        """Import from saham.db → global::dividends (if table exists)."""
        print("Importing dividends...")
        conn = self._connect_source()
        try:
            df = pd.read_sql_query("SELECT * FROM dividends", conn)
        except Exception:
            conn.close()
            self._log("dividends", 0)
            return
        conn.close()

        if df.empty:
            self._log("dividends", 0)
            return

        rows = []
        for _, r in df.iterrows():
            rows.append((
                r.get("ticker"), r.get("ex_date"), r.get("record_date"),
                r.get("payment_date"), float(r.get("amount", 0) or 0),
                r.get("currency", "IDR"), r.get("frequency", ""),
                "saham_db",
            ))

        sql = """INSERT OR REPLACE INTO dividends
            (ticker, ex_date, record_date, payment_date, amount,
             currency, frequency, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""
        n = self.storage.executemany_batch(sql, rows)
        self._log("dividends", n)

    def _import_journal_entries(self):
        """Import from saham.db::journal_entries → global::trade_journal."""
        print("Importing journal_entries...")
        conn = self._connect_source()
        try:
            df = pd.read_sql_query("SELECT * FROM journal_entries", conn)
        except Exception:
            conn.close()
            self._log("trade_journal", 0)
            return
        conn.close()

        if df.empty:
            self._log("trade_journal", 0)
            return

        rows = []
        for _, r in df.iterrows():
            rows.append((
                r.get("ticker"), r.get("entry_date"), r.get("exit_date"),
                float(r.get("entry_price", 0) or 0),
                float(r.get("exit_price", 0) or 0),
                float(r.get("position_size", 0) or 0),
                r.get("side", ""),
                float(r.get("pnl", 0) or 0),
                float(r.get("pnl_pct", 0) or 0),
                r.get("setup_type", ""),
                r.get("notes", ""),
                r.get("emotional_state", ""),
                datetime.now(UTC).isoformat(),
            ))

        sql = """INSERT OR REPLACE INTO trade_journal
            (ticker, entry_date, exit_date, entry_price, exit_price,
             quantity, side, pnl, return_pct, strategy, notes, tags, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        n = self.storage.executemany_batch(sql, rows)
        self._log("trade_journal", n)


def run_import(source_db: str = "C:/xampp/htdocs/pasar_modal/data/saham.db"):
    """Run the full import pipeline."""
    print("=== Legacy Data Import ===")
    print(f"Source: {source_db}")
    print()

    importer = LegacyDataImporter(source_db=source_db)
    stats = importer.import_all()

    print()
    print("=== Import Summary ===")
    total = 0
    for table, n in stats.items():
        print(f"  {table}: {n} rows")
        total += n
    print(f"  TOTAL: {total} rows imported")
    return stats


if __name__ == "__main__":
    run_import()
