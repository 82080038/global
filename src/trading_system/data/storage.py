"""Data Storage menggunakan SQLite (Phase 1).

Nantinya dapat diganti TimescaleDB/InfluxDB tanpa mengubah kontrak fungsi.
"""

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from trading_system.config import DB_PATH, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS ohlcv (
    ticker TEXT,
    asset_class TEXT,
    exchange TEXT,
    timestamp TEXT,
    timeframe TEXT,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    adjusted_close REAL,
    source TEXT,
    ingested_at TEXT,
    data_quality_score REAL,
    PRIMARY KEY (ticker, timestamp, timeframe)
);

CREATE TABLE IF NOT EXISTS source_health (
    source TEXT PRIMARY KEY,
    last_success TEXT,
    last_error TEXT,
    status TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT,
    payload TEXT,
    timestamp TEXT,
    actor TEXT
);

CREATE TABLE IF NOT EXISTS scores (
    ticker TEXT,
    engine TEXT,
    score REAL,
    breakdown TEXT,
    as_of TEXT,
    PRIMARY KEY (ticker, engine, as_of)
);

CREATE TABLE IF NOT EXISTS relationship_matrix (
    asset_a TEXT,
    asset_b TEXT,
    window INTEGER,
    correlation REAL,
    lag INTEGER,
    updated_at TEXT,
    PRIMARY KEY (asset_a, asset_b, window)
);

CREATE TABLE IF NOT EXISTS render_log (
    ticker TEXT NOT NULL,
    table_name TEXT NOT NULL,
    last_rendered TEXT NOT NULL,
    rows_rendered INTEGER DEFAULT 0,
    status TEXT DEFAULT 'ok',
    PRIMARY KEY (ticker, table_name)
);

CREATE TABLE IF NOT EXISTS corporate_actions (
    ticker TEXT,
    action_type TEXT,
    announce_date TEXT,
    ex_date TEXT,
    record_date TEXT,
    payment_date TEXT,
    value REAL,
    unit TEXT,
    source TEXT,
    PRIMARY KEY (ticker, action_type, ex_date)
);

CREATE TABLE IF NOT EXISTS news (
    news_id TEXT PRIMARY KEY,
    headline TEXT,
    body TEXT,
    published_at TEXT,
    source TEXT,
    entities TEXT,
    topic TEXT,
    sentiment REAL,
    impact REAL
);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    quantity REAL NOT NULL DEFAULT 0,
    avg_entry_price REAL NOT NULL DEFAULT 0,
    current_price REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'OPEN',
    stop_loss REAL,
    take_profit REAL,
    trailing_stop_pct REAL DEFAULT 0.05,
    highest_price_since_entry REAL,
    realized_pnl REAL DEFAULT 0,
    unrealized_pnl REAL DEFAULT 0,
    return_pct REAL DEFAULT 0,
    opened_at TEXT,
    closed_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    order_type TEXT NOT NULL,
    order_style TEXT DEFAULT 'MARKET',
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    total_value REAL NOT NULL,
    fee REAL DEFAULT 0,
    slippage REAL DEFAULT 0,
    realized_pnl REAL DEFAULT 0,
    status TEXT DEFAULT 'FILLED',
    trigger TEXT DEFAULT 'MANUAL',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS equity_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    equity REAL NOT NULL,
    cash REAL DEFAULT 0,
    positions_value REAL DEFAULT 0,
    realized_pnl REAL DEFAULT 0,
    unrealized_pnl REAL DEFAULT 0,
    total_return_pct REAL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL UNIQUE,
    is_favorite INTEGER DEFAULT 0,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_weights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT,
    weights_json TEXT NOT NULL,
    r2_score REAL,
    n_samples INTEGER,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp);

CREATE TABLE IF NOT EXISTS daily_risk_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    var_95 REAL,
    var_99 REAL,
    cvar_95 REAL,
    cvar_99 REAL,
    max_drawdown REAL,
    annualized_volatility REAL,
    portfolio_value REAL,
    created_at TEXT NOT NULL
);

-- D1-D31 tables for legacy data import (§13.4 #3, P2-3)
CREATE TABLE IF NOT EXISTS instrument_master (
    ticker TEXT PRIMARY KEY, name TEXT, sector TEXT, subsector TEXT,
    exchange TEXT, listing_date TEXT, delisting_date TEXT,
    is_active INTEGER DEFAULT 1, board TEXT, market_cap REAL,
    free_float REAL, asset_class TEXT DEFAULT 'equity', updated_at TEXT,
    ipo_date TEXT, ipo_price REAL, status TEXT DEFAULT 'active',
    lock_up_end_date TEXT
);
CREATE TABLE IF NOT EXISTS fundamental_data (
    ticker TEXT, date TEXT, pe_ratio REAL, pb_ratio REAL, roe REAL,
    debt_to_equity REAL, dividend_yield REAL, earnings_per_share REAL,
    book_value_per_share REAL, net_profit REAL, revenue REAL,
    total_assets REAL, total_liabilities REAL, cash_flow REAL,
    fiscal_year INTEGER, quarter INTEGER, source TEXT,
    PRIMARY KEY (ticker, date, source)
);
CREATE TABLE IF NOT EXISTS macro_data (
    series_name TEXT, date TEXT, value REAL, unit TEXT,
    source TEXT, frequency TEXT, PRIMARY KEY (series_name, date, source)
);
CREATE TABLE IF NOT EXISTS foreign_flow (
    ticker TEXT, date TEXT, foreign_buy REAL, foreign_sell REAL,
    foreign_net REAL, domestic_buy REAL, domestic_sell REAL,
    domestic_net REAL, source TEXT, PRIMARY KEY (ticker, date, source)
);
CREATE TABLE IF NOT EXISTS broker_flow (
    ticker TEXT, date TEXT, broker TEXT, buy_volume REAL, buy_value REAL,
    sell_volume REAL, sell_value REAL, net_volume REAL, net_value REAL,
    source TEXT, PRIMARY KEY (ticker, date, broker, source)
);
CREATE TABLE IF NOT EXISTS policy_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, event_type TEXT,
    description TEXT, impact TEXT, source TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dividends (
    ticker TEXT, ex_date TEXT, record_date TEXT, payment_date TEXT,
    amount REAL, currency TEXT, frequency TEXT, source TEXT,
    PRIMARY KEY (ticker, ex_date, source)
);
CREATE TABLE IF NOT EXISTS sector_master (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kode TEXT, nama TEXT,
    deskripsi TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS market_calendar (
    date TEXT PRIMARY KEY, exchange TEXT, is_trading_day INTEGER DEFAULT 1,
    holiday_name TEXT, half_day INTEGER DEFAULT 0, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS fear_greed (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tanggal TEXT,
    nilai INTEGER, label TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS external_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tanggal TEXT, kategori TEXT,
    judul TEXT, lokasi TEXT, dampak_market TEXT, sektor TEXT,
    deskripsi TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS esg_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kode TEXT, year INTEGER,
    rating_agency TEXT, rating TEXT, score REAL, created_at TEXT
);
CREATE TABLE IF NOT EXISTS corporate_governance (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kode TEXT, year INTEGER,
    board_commissioners REAL, independent_commissioners REAL,
    board_directors REAL, audit_committee_meetings REAL,
    gcg_score TEXT, acgs_score TEXT, has_whistleblowing INTEGER,
    has_risk_committee INTEGER, created_at TEXT
);
CREATE TABLE IF NOT EXISTS stock_personality (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kode TEXT, profile_date TEXT,
    avg_daily_volatility REAL, volatility_regime TEXT, trend_bias TEXT,
    trend_strength REAL, avg_uptrend_streak INTEGER, avg_downtrend_streak INTEGER,
    beta_vs_ihsg REAL, correlation_ihsg REAL, avg_volume REAL,
    volume_consistency REAL, net_distribution_score REAL, liquidity_score REAL,
    best_pattern TEXT, best_pattern_winrate REAL, worst_pattern TEXT,
    worst_pattern_winrate REAL, overall_pattern_winrate REAL,
    personality_label TEXT, total_patterns_detected INTEGER,
    total_patterns_success INTEGER, created_at TEXT
);
CREATE TABLE IF NOT EXISTS trade_journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, entry_date TEXT,
    exit_date TEXT, entry_price REAL, exit_price REAL, quantity REAL,
    side TEXT, pnl REAL, return_pct REAL, strategy TEXT, notes TEXT,
    tags TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pattern_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, date TEXT,
    pattern_type TEXT, confidence REAL, direction TEXT, details TEXT,
    source TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS valuation_cache (
    ticker TEXT, date TEXT, method TEXT, intrinsic_value REAL,
    market_price REAL, upside_pct REAL, assumptions TEXT, source TEXT,
    PRIMARY KEY (ticker, date, method, source)
);
CREATE TABLE IF NOT EXISTS technical_indicators (
    ticker TEXT, date TEXT, indicator TEXT, value REAL, timeframe TEXT,
    source TEXT, PRIMARY KEY (ticker, date, indicator, timeframe, source)
);
CREATE INDEX IF NOT EXISTS idx_fundamental_ticker ON fundamental_data(ticker);
CREATE INDEX IF NOT EXISTS idx_fundamental_date ON fundamental_data(date);
CREATE INDEX IF NOT EXISTS idx_macro_series ON macro_data(series_name);
CREATE INDEX IF NOT EXISTS idx_macro_date ON macro_data(date);
CREATE INDEX IF NOT EXISTS idx_foreign_flow_ticker ON foreign_flow(ticker);
CREATE INDEX IF NOT EXISTS idx_foreign_flow_date ON foreign_flow(date);
CREATE INDEX IF NOT EXISTS idx_dividends_ticker ON dividends(ticker);
CREATE INDEX IF NOT EXISTS idx_trade_journal_ticker ON trade_journal(ticker);
CREATE INDEX IF NOT EXISTS idx_technical_indicators_ticker ON technical_indicators(ticker);
CREATE INDEX IF NOT EXISTS idx_technical_indicators_date ON technical_indicators(date);

-- Trading suspensions (§13.4 — IPO/suspension/delisting lifecycle)
CREATE TABLE IF NOT EXISTS trading_suspensions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    suspend_date TEXT NOT NULL,
    resume_date TEXT,
    reason TEXT,
    suspension_type TEXT,
    source TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_suspension_ticker ON trading_suspensions(ticker);
CREATE INDEX IF NOT EXISTS idx_suspension_date ON trading_suspensions(suspend_date);
"""


class DataStorage:
    """SQLite storage with raw/clean zone support."""

    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = Path(db_path)
        ensure_dirs()
        self._init_db()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        self._migrate_legacy_tables()
        with self._connect() as conn:
            conn.executescript(SCHEMA)
        # Set WAL as persistent journal mode (database-level, not per-connection)
        # WAL allows concurrent reads during writes — critical for large imports (P2-3).
        with self._connect() as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            if mode.lower() != "wal":
                conn.execute("PRAGMA journal_mode = WAL")
            # Set synchronous=NORMAL for WAL (safe + faster than FULL)
            conn.execute("PRAGMA synchronous = NORMAL")
            # Cache size 64MB for better import performance
            conn.execute("PRAGMA cache_size = -65536")

    def _migrate_legacy_tables(self):
        """Rename legacy tables with incompatible schemas to _legacy_backup.

        Tables imported from pasar_modal had different column names (e.g.,
        trade_journal used 'kode' instead of 'ticker'). CREATE TABLE IF NOT EXISTS
        won't fix them, so we rename them to preserve data while allowing new
        schema tables to be created.
        """
        # Map: new_table_name -> list of old column names that indicate legacy schema
        legacy_indicators = {
            "trade_journal": ["kode", "trader_id"],
            "pattern_analysis": ["kode", "personality_label"],
            "technical_indicators": ["kode", "tanggal"],
            "fundamental_data": ["kode", "periode"],
            "foreign_flow": ["tanggal", "beli"],
            "broker_flow": ["tanggal", "kode"],
            "macro_data": ["periode", "suku_bunga"],
            "instrument_master": ["kode", "nama"],
        }
        with self._connect() as conn:
            for table, old_cols in legacy_indicators.items():
                # Check if table exists
                exists = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ).fetchone()
                if not exists:
                    continue
                # Check if it has legacy columns
                cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
                col_names = {c[1] for c in cols}
                if any(c in col_names for c in old_cols):
                    backup_name = f"{table}_legacy_backup"
                    # Check if backup already exists
                    backup_exists = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                        (backup_name,),
                    ).fetchone()
                    if backup_exists:
                        # Backup already exists from previous run — just drop the old table
                        conn.execute(f"DROP TABLE {table}")
                    else:
                        conn.execute(f"ALTER TABLE {table} RENAME TO {backup_name}")

    # ---------- Scores ----------
    def save_score(self, ticker: str, engine: str, score: float, breakdown: dict, as_of: str | None = None):
        import json
        from datetime import datetime

        if as_of is None:
            as_of = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO scores (ticker, engine, score, breakdown, as_of) VALUES (?, ?, ?, ?, ?)",
                (ticker, engine, round(float(score), 4), json.dumps(breakdown, default=str), as_of),
            )

    def load_scores(self, ticker: str | None = None, engine: str | None = None) -> pd.DataFrame:
        sql = "SELECT * FROM scores"
        params = []
        conditions = []
        if ticker:
            conditions.append("ticker = ?")
            params.append(ticker)
        if engine:
            conditions.append("engine = ?")
            params.append(engine)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY as_of DESC"
        with self._connect() as conn:
            return pd.read_sql_query(sql, conn, params=params)

    # ---------- Relationship ----------
    def save_relationship(self, asset_a: str, asset_b: str, window: int, correlation: float, lag: int, updated_at: str | None = None):
        from datetime import datetime

        if updated_at is None:
            updated_at = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO relationship_matrix (asset_a, asset_b, window, correlation, lag, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (asset_a, asset_b, window, round(float(correlation), 4), int(lag), updated_at),
            )

    def load_relationships(self, asset_a: str | None = None, asset_b: str | None = None) -> pd.DataFrame:
        sql = "SELECT * FROM relationship_matrix"
        params = []
        conditions = []
        if asset_a:
            conditions.append("asset_a = ?")
            params.append(asset_a)
        if asset_b:
            conditions.append("asset_b = ?")
            params.append(asset_b)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY updated_at DESC"
        with self._connect() as conn:
            return pd.read_sql_query(sql, conn, params=params)

    # ---------- Corporate Actions ----------
    def save_corporate_action(self, record: dict):
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO corporate_actions (ticker, action_type, announce_date, ex_date, record_date, payment_date, value, unit, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.get("ticker"),
                    record.get("action_type"),
                    record.get("announce_date"),
                    record.get("ex_date"),
                    record.get("record_date"),
                    record.get("payment_date"),
                    record.get("value"),
                    record.get("unit"),
                    record.get("source"),
                ),
            )

    def load_corporate_actions(self, ticker: str) -> pd.DataFrame:
        with self._connect() as conn:
            return pd.read_sql_query(
                "SELECT * FROM corporate_actions WHERE ticker = ? ORDER BY ex_date DESC",
                conn, params=[ticker]
            )

    # ---------- OHLCV ----------
    def save_ohlcv(self, df: pd.DataFrame) -> int:
        """Menyimpan DataFrame OHLCV ke tabel clean."""
        if df.empty:
            return 0
        required = {"ticker", "timestamp", "open", "high", "low", "close", "volume", "source"}
        if not required.issubset(df.columns):
            raise ValueError(f"DataFrame OHLCV wajib memiliki kolom: {required}")
        df = df.copy()
        if "ingested_at" not in df.columns:
            df["ingested_at"] = None
        if "adjusted_close" not in df.columns:
            df["adjusted_close"] = df["close"]
        rows = [
            (
                row.get("ticker"), row.get("asset_class", "equity"),
                row.get("exchange", "IDX"), row.get("timestamp"),
                row.get("timeframe", "1d"), float(row.get("open")),
                float(row.get("high")), float(row.get("low")),
                float(row.get("close")), float(row.get("volume")),
                float(row.get("adjusted_close")),
                row.get("source"), row.get("ingested_at"),
                row.get("data_quality_score"),
            )
            for _, row in df.iterrows()
        ]
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO ohlcv
                (ticker, asset_class, exchange, timestamp, timeframe, open, high, low,
                 close, volume, adjusted_close, source, ingested_at, data_quality_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        n = len(df)

        # Auto-sync: export updated tickers to Parquet archive
        self._sync_ohlcv_to_parquet(df)

        return n

    def _sync_ohlcv_to_parquet(self, df: pd.DataFrame) -> None:
        """Sync updated OHLCV data to Parquet archive (best-effort, non-blocking).

        Also cleans up old raw zone Parquet files for synced tickers to prevent
        accumulation from repeated Yahoo Finance fetches.
        """
        import os
        sync_enabled = os.getenv("PARQUET_AUTO_SYNC", "1")
        if sync_enabled != "1":
            return
        try:
            from trading_system.config import DATA_ARCHIVE_DIR, RAW_ZONE
            archive_dir = DATA_ARCHIVE_DIR / "ohlcv"
            archive_dir.mkdir(parents=True, exist_ok=True)
            # Export full data per ticker (not just the new rows) to keep Parquet complete
            conn = sqlite3.connect(str(self.db_path))
            for ticker in df["ticker"].unique():
                full_df = pd.read_sql_query(
                    "SELECT * FROM ohlcv WHERE ticker = ? ORDER BY timestamp",
                    conn,
                    params=(ticker,),
                )
                if full_df.empty:
                    continue
                # Delete old per-ticker files in archive
                base = ticker.replace(".JK", "")
                for pattern in [f"{ticker}*.parquet", f"{base}*.parquet"]:
                    for f in archive_dir.glob(pattern):
                        try:
                            f.unlink()
                        except Exception:
                            pass
                # Write fresh complete file
                from datetime import datetime as _dt
                ts = _dt.now(UTC).strftime("%Y%m%d%H%M%S")
                out_file = archive_dir / f"{ticker}_{ts}.parquet"
                full_df.to_parquet(out_file, index=False, compression="snappy")
                # Cleanup old raw zone files for this ticker (keep only latest)
                raw_files = sorted(
                    RAW_ZONE.glob(f"{ticker}_*.parquet"),
                    key=lambda f: f.stat().st_mtime,
                    reverse=True,
                )
                # Also check base name without .JK
                raw_files_base = sorted(
                    RAW_ZONE.glob(f"{base}_*.parquet"),
                    key=lambda f: f.stat().st_mtime,
                    reverse=True,
                )
                all_raw = raw_files + raw_files_base
                for old_f in all_raw[1:]:  # keep newest, delete rest
                    try:
                        old_f.unlink()
                    except Exception:
                        pass
            conn.close()
        except Exception:
            pass  # non-fatal: Parquet sync is best-effort

    def _sync_table_to_parquet(self, table: str, archive_subdir: str | None = None) -> None:
        """Sync a full table to Parquet archive (best-effort, non-blocking).

        Used for non-OHLCV tables like instrument_master, trading_suspensions.
        Writes a single Parquet file per table (not per-ticker).
        """
        import os
        sync_enabled = os.getenv("PARQUET_AUTO_SYNC", "1")
        if sync_enabled != "1":
            return
        try:
            from trading_system.config import DATA_ARCHIVE_DIR
            subdir = archive_subdir or table
            archive_dir = DATA_ARCHIVE_DIR / subdir
            archive_dir.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.db_path))
            full_df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
            if full_df.empty:
                conn.close()
                return
            # Delete old file(s)
            for f in archive_dir.glob(f"{table}*.parquet"):
                try:
                    f.unlink()
                except Exception:
                    pass
            from datetime import datetime as _dt
            ts = _dt.now(UTC).strftime("%Y%m%d%H%M%S")
            out_file = archive_dir / f"{table}_{ts}.parquet"
            full_df.to_parquet(out_file, index=False, compression="snappy")
            conn.close()
        except Exception:
            pass  # non-fatal: Parquet sync is best-effort

    def update_adjusted_close(self, ticker: str) -> int:
        """Recompute and persist adjusted_close for a ticker using corporate actions.

        Uses CorporateActionEngine.compute_adjustment_factor to calculate the
        cumulative adjustment factor (split + dividend), then updates the
        adjusted_close column in the ohlcv table (§4.3 SARAN_PENGEMBANGAN.md).

        Returns the number of rows updated.
        """
        from trading_system.corporate.actions import CorporateActionEngine

        engine = CorporateActionEngine(self)
        df = engine.compute_adjustment_factor(ticker)
        if df.empty:
            return 0

        rows = []
        for ts, row in df.iterrows():
            ts_str = ts.strftime("%Y-%m-%d %H:%M:%S") if hasattr(ts, "strftime") else str(ts)
            rows.append((float(row["adj_close"]), ts_str, ticker))

        with self._connect() as conn:
            conn.executemany(
                "UPDATE ohlcv SET adjusted_close = ? WHERE timestamp = ? AND ticker = ?",
                rows,
            )
        return len(rows)

    def executemany_batch(
        self,
        sql: str,
        rows: list[tuple],
        batch_size: int = 5000,
    ) -> int:
        """Execute executemany in batches to avoid SQLite "too many SQL variables" error.

        Also wraps each batch in a single transaction for performance.
        Returns total number of rows affected.
        """
        if not rows:
            return 0
        total = 0
        with self._connect() as conn:
            for i in range(0, len(rows), batch_size):
                batch = rows[i : i + batch_size]
                conn.executemany(sql, batch)
                total += len(batch)
        return total

    def load_ohlcv(
        self,
        ticker: str,
        start: str | None = None,
        end: str | None = None,
        timeframe: str = "1d",
        limit: int | None = None,
    ) -> pd.DataFrame:
        """Memuat OHLCV sebagai DataFrame."""
        sql = "SELECT * FROM ohlcv WHERE ticker = ? AND timeframe = ?"
        params = [ticker, timeframe]
        if start:
            sql += " AND timestamp >= ?"
            params.append(start)
        if end:
            sql += " AND timestamp <= ?"
            params.append(end)
        if limit is not None:
            # Ambil N baris terbaru (ORDER BY timestamp DESC LIMIT ?), lalu
            # bungkus dalam subquery agar hasil akhir tetap urut ascending.
            sql += " ORDER BY timestamp DESC LIMIT ?"
            sql = f"SELECT * FROM ({sql}) sub ORDER BY timestamp"
            params.append(int(limit))
        else:
            sql += " ORDER BY timestamp"
        with self._connect() as conn:
            df = pd.read_sql_query(sql, conn, params=params)
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"], format="mixed", errors="coerce")
            df.set_index("timestamp", inplace=True)
        return df

    def list_tickers(self) -> list[str]:
        with self._connect() as conn:
            cur = conn.execute("SELECT DISTINCT ticker FROM ohlcv ORDER BY ticker")
            return [r[0] for r in cur.fetchall()]

    # ---------- Source Health ----------
    def update_source_health(self, source: str, status: str, success: bool):
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            if status == "ok":
                conn.execute(
                    """
                    INSERT INTO source_health (source, last_success, last_error, status)
                    VALUES (?, ?, NULL, ?)
                    ON CONFLICT(source) DO UPDATE SET
                        last_success = excluded.last_success,
                        status = excluded.status
                    """,
                    (source, now, status),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO source_health (source, last_success, last_error, status)
                    VALUES (?, NULL, ?, ?)
                    ON CONFLICT(source) DO UPDATE SET
                        last_error = excluded.last_error,
                        status = excluded.status
                    """,
                    (source, now, status),
                )

    def get_source_health(self) -> pd.DataFrame:
        with self._connect() as conn:
            return pd.read_sql_query("SELECT * FROM source_health", conn)

    # ---------- Render Log (staleness tracking) ----------
    def log_render(self, ticker: str, table_name: str, rows: int = 0, status: str = "ok"):
        """Record that a ticker's table was rendered at the current time."""
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO render_log (ticker, table_name, last_rendered, rows_rendered, status)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(ticker, table_name) DO UPDATE SET
                     last_rendered = excluded.last_rendered,
                     rows_rendered = excluded.rows_rendered,
                     status = excluded.status""",
                (ticker, table_name, now, rows, status),
            )

    def get_last_rendered(self, ticker: str, table_name: str) -> str | None:
        """Get ISO timestamp of last render for a ticker/table, or None if never rendered."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT last_rendered FROM render_log WHERE ticker = ? AND table_name = ?",
                (ticker, table_name),
            ).fetchone()
            return row[0] if row else None

    def get_stale_tickers(
        self, table_name: str, tickers: list[str], max_age_hours: float = 24
    ) -> list[str]:
        """Return tickers that haven't been rendered for this table in the last max_age_hours.
        Tickers with no render_log entry are always considered stale."""
        from datetime import timedelta
        cutoff = (datetime.now(UTC) - timedelta(hours=max_age_hours)).isoformat()
        with self._connect() as conn:
            rendered = set(
                r[0]
                for r in conn.execute(
                    "SELECT ticker FROM render_log WHERE table_name = ? AND last_rendered >= ?",
                    (table_name, cutoff),
                ).fetchall()
            )
        return [t for t in tickers if t not in rendered]

    # ---------- Audit ----------
    def audit(self, event_type: str, payload: Any, actor: str = "system"):
        import json
        from datetime import datetime

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO audit_log (event_type, payload, timestamp, actor) VALUES (?, ?, ?, ?)",
                (event_type, json.dumps(payload, default=str), datetime.now(UTC).isoformat(), actor),
            )

    # ---------- Positions ----------
    def save_position(self, ticker: str, quantity: float, avg_entry_price: float,
                      stop_loss: float | None = None, take_profit: float | None = None,
                      trailing_stop_pct: float = 0.05) -> int:
        """Create a new position. Returns position id."""
        from datetime import datetime
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO positions (ticker, quantity, avg_entry_price, current_price,
                    status, stop_loss, take_profit, trailing_stop_pct, highest_price_since_entry,
                    opened_at, created_at)
                    VALUES (?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, ?)""",
                (ticker, quantity, avg_entry_price, avg_entry_price,
                 stop_loss, take_profit, trailing_stop_pct, avg_entry_price, now, now),
            )
            return cursor.lastrowid

    def get_open_position(self, ticker: str) -> dict | None:
        """Get the open position for a ticker."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM positions WHERE ticker = ? AND status = 'OPEN' ORDER BY id DESC LIMIT 1",
                (ticker,),
            ).fetchone()
            if row:
                cols = [d[0] for d in conn.execute("SELECT * FROM positions WHERE ticker = ? AND status = 'OPEN' ORDER BY id DESC LIMIT 1", (ticker,)).description]
                return dict(zip(cols, row))
            return None

    def get_all_open_positions(self) -> list[dict]:
        """Get all open positions."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM positions WHERE status = 'OPEN' ORDER BY opened_at DESC"
            ).fetchall()
            if not rows:
                return []
            cols = [d[0] for d in conn.execute("SELECT * FROM positions WHERE status = 'OPEN' ORDER BY opened_at DESC").description]
            return [dict(zip(cols, row)) for row in rows]

    def get_open_position_by_id(self, position_id: int) -> dict | None:
        """Get a position by ID (any status)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM positions WHERE id = ?", (position_id,)
            ).fetchone()
            if row:
                cols = [d[0] for d in conn.execute(
                    "SELECT * FROM positions WHERE id = ?", (position_id,)
                ).description]
                return dict(zip(cols, row))
            return None

    # Allowlist of columns that may be updated on the positions table.
    # Defends against SQL injection via kwarg keys (identifiers cannot be
    # parameterized in SQLite, so they are interpolated into the query string).
    _POSITION_COLUMNS = {
        "ticker", "quantity", "avg_entry_price", "current_price", "status",
        "stop_loss", "take_profit", "trailing_stop_pct",
        "highest_price_since_entry", "realized_pnl", "unrealized_pnl",
        "return_pct", "opened_at", "closed_at", "created_at",
    }

    def update_position(self, position_id: int, **kwargs):
        """Update position fields."""
        from datetime import datetime
        if "closed_at" not in kwargs and kwargs.get("status") == "CLOSED":
            kwargs["closed_at"] = datetime.now(UTC).isoformat()
        # Reject any column name not in the allowlist to prevent SQL injection
        # via identifier interpolation.
        bad = set(kwargs) - self._POSITION_COLUMNS
        if bad:
            raise ValueError(f"Invalid position columns: {sorted(bad)}")
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [position_id]
        with self._connect() as conn:
            conn.execute(f"UPDATE positions SET {sets} WHERE id = ?", vals)

    # ---------- Orders ----------
    def save_order(self, ticker: str, order_type: str, quantity: float, price: float,
                   fee: float = 0, slippage: float = 0, trigger: str = "MANUAL",
                   order_style: str = "MARKET", status: str = "FILLED",
                   realized_pnl: float = 0) -> int:
        """Save an executed order. Returns order id.

        `realized_pnl` disimpan langsung pada baris SELL agar perhitungan daily
        loss limit tidak perlu mengestimasi harga beli dari rata-rata historis
        (§3.4 SARAN_PENGEMBANGAN.md).
        """
        from datetime import datetime
        now = datetime.now(UTC).isoformat()
        total_value = quantity * price
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO orders (ticker, order_type, order_style, quantity, price,
                    total_value, fee, slippage, realized_pnl, status, trigger, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (ticker, order_type, order_style, quantity, price,
                 total_value, fee, slippage, realized_pnl, status, trigger, now),
            )
            return cursor.lastrowid

    def get_orders(self, ticker: str | None = None, limit: int = 100) -> list[dict]:
        """Get order history."""
        with self._connect() as conn:
            if ticker:
                cursor = conn.execute(
                    "SELECT * FROM orders WHERE ticker = ? ORDER BY id DESC LIMIT ?", (ticker, limit)
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,)
                )
            cols = [d[0] for d in cursor.description]
            rows = cursor.fetchall()
            return [dict(zip(cols, row)) for row in rows]

    # ---------- System State (key-value, untuk flag persisten lintas siklus) ----------
    def set_state(self, key: str, value: str) -> None:
        """Simpan flag/state persisten (mis. circuit breaker halt-for-today)."""
        from datetime import datetime
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO system_state (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (key, value, now),
            )

    def get_state(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM system_state WHERE key = ?", (key,)).fetchone()
            return row[0] if row else None

    # ---------- Equity Snapshots ----------
    def save_equity_snapshot(self, equity: float, cash: float = 0, positions_value: float = 0,
                             realized_pnl: float = 0, unrealized_pnl: float = 0,
                             total_return_pct: float = 0) -> int:
        """Save a daily equity snapshot for performance tracking."""
        from datetime import datetime
        now = datetime.now(UTC).isoformat()
        today = datetime.now(UTC).date().isoformat()
        with self._connect() as conn:
            conn.execute("DELETE FROM equity_snapshots WHERE date = ?", (today,))
            cursor = conn.execute(
                """INSERT INTO equity_snapshots (date, equity, cash, positions_value,
                    realized_pnl, unrealized_pnl, total_return_pct, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (today, equity, cash, positions_value, realized_pnl,
                 unrealized_pnl, total_return_pct, now),
            )
            return cursor.lastrowid

    def get_equity_snapshots(self, limit: int = 90) -> list[dict]:
        """Get equity snapshots for charting."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM equity_snapshots ORDER BY date ASC LIMIT ?", (limit,)
            ).fetchall()
            if not rows:
                return []
            cols = [d[0] for d in conn.execute(
                "SELECT * FROM equity_snapshots ORDER BY date ASC LIMIT ?", (limit,)
            ).description]
            return [dict(zip(cols, row)) for row in rows]

    # ---------- Watchlist ----------
    def add_to_watchlist(self, ticker: str, notes: str | None = None) -> int:
        """Add a ticker to the watchlist."""
        from datetime import datetime
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO watchlist (ticker, is_favorite, notes, created_at)
                    VALUES (?, 1, ?, ?)
                    ON CONFLICT(ticker) DO UPDATE SET is_favorite = 1""",
                (ticker, notes, now),
            )
            return cursor.lastrowid

    def remove_from_watchlist(self, ticker: str) -> bool:
        """Remove a ticker from favorites (unfavorite)."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE watchlist SET is_favorite = 0 WHERE ticker = ?", (ticker,)
            )
            return True

    def update_watchlist(self, ticker: str, **kwargs) -> bool:
        """Update watchlist fields (notes, is_favorite)."""
        allowed = {"notes", "is_favorite"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        sets = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [ticker]
        with self._connect() as conn:
            conn.execute(f"UPDATE watchlist SET {sets} WHERE ticker = ?", vals)
            return True

    def toggle_watchlist(self, ticker: str) -> bool:
        """Toggle favorite status. Returns new is_favorite state."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT is_favorite FROM watchlist WHERE ticker = ?", (ticker,)
            ).fetchone()
            if row is None:
                from datetime import datetime
                now = datetime.now(UTC).isoformat()
                conn.execute(
                    "INSERT INTO watchlist (ticker, is_favorite, created_at) VALUES (?, 1, ?)",
                    (ticker, now),
                )
                return True
            else:
                new_val = 0 if row[0] else 1
                conn.execute(
                    "UPDATE watchlist SET is_favorite = ? WHERE ticker = ?", (new_val, ticker)
                )
                return bool(new_val)

    def get_watchlist(self, favorites_only: bool = True) -> list[dict]:
        """Get watchlist tickers."""
        with self._connect() as conn:
            query = ("SELECT * FROM watchlist WHERE is_favorite = 1 ORDER BY ticker"
                     if favorites_only else "SELECT * FROM watchlist ORDER BY ticker")
            rows = conn.execute(query).fetchall()
            if not rows:
                return []
            cols = [d[0] for d in conn.execute(query).description]
            return [dict(zip(cols, row)) for row in rows]

    # ---------- AI Weights ----------
    def save_ai_weights(self, weights: dict, ticker: str | None = None,
                        r2_score: float = 0.0, n_samples: int = 0) -> int:
        """Save AI-optimized weights to DB."""
        import json
        from datetime import datetime
        now = datetime.now(UTC).isoformat()
        weights_json = json.dumps(weights)
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO ai_weights (ticker, weights_json, r2_score, n_samples, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (ticker, weights_json, r2_score, n_samples, now),
            )
            return cursor.lastrowid

    def get_ai_weights(self, ticker: str | None = None, max_age_days: int = 7) -> dict | None:
        """Get most recent AI weights younger than max_age_days. Returns None if stale or missing."""
        import json
        from datetime import datetime, timedelta
        cutoff = (datetime.now(UTC) - timedelta(days=max_age_days)).isoformat()
        with self._connect() as conn:
            if ticker:
                row = conn.execute(
                    "SELECT weights_json FROM ai_weights WHERE ticker = ? AND created_at > ? ORDER BY id DESC LIMIT 1",
                    (ticker, cutoff),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT weights_json FROM ai_weights WHERE ticker IS NULL AND created_at > ? ORDER BY id DESC LIMIT 1",
                    (cutoff,),
                ).fetchone()
            if row:
                return json.loads(row[0])
            return None

    # ---------- Daily Risk Metrics ----------
    def save_daily_risk_metrics(self, var_95: float, var_99: float,
                                cvar_95: float, cvar_99: float,
                                max_drawdown: float, annualized_volatility: float,
                                portfolio_value: float = 0.0) -> int:
        """Save daily portfolio risk metrics."""
        from datetime import datetime
        now = datetime.now(UTC).isoformat()
        today = datetime.now(UTC).date().isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO daily_risk_metrics
                   (date, var_95, var_99, cvar_95, cvar_99, max_drawdown,
                    annualized_volatility, portfolio_value, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(date) DO UPDATE SET
                    var_95=excluded.var_95, var_99=excluded.var_99,
                    cvar_95=excluded.cvar_95, cvar_99=excluded.cvar_99,
                    max_drawdown=excluded.max_drawdown,
                    annualized_volatility=excluded.annualized_volatility,
                    portfolio_value=excluded.portfolio_value,
                    created_at=excluded.created_at""",
                (today, var_95, var_99, cvar_95, cvar_99, max_drawdown,
                 annualized_volatility, portfolio_value, now),
            )
            return cursor.lastrowid

    def get_daily_risk_metrics(self, limit: int = 30) -> list[dict]:
        """Get recent daily risk metrics."""
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM daily_risk_metrics ORDER BY date DESC LIMIT ?", (limit,)
            )
            cols = [d[0] for d in cursor.description]
            rows = cursor.fetchall()
            return [dict(zip(cols, row)) for row in rows]

    # ---------- Delete operations (CRUD completeness) ----------
    def delete_ohlcv(self, ticker: str, timeframe: str = "1d") -> int:
        """Delete all OHLCV rows for a ticker. Returns number of rows deleted."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM ohlcv WHERE ticker = ? AND timeframe = ?",
                (ticker, timeframe),
            )
            return cursor.rowcount

    def delete_scores(self, ticker: str | None = None, engine: str | None = None) -> int:
        """Delete scores. If no filters, deletes all. Returns rows deleted."""
        sql = "DELETE FROM scores"
        params: list = []
        conditions: list[str] = []
        if ticker:
            conditions.append("ticker = ?")
            params.append(ticker)
        if engine:
            conditions.append("engine = ?")
            params.append(engine)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        with self._connect() as conn:
            cursor = conn.execute(sql, params)
            return cursor.rowcount

    def delete_orders(self, ticker: str | None = None, before_date: str | None = None) -> int:
        """Delete orders, optionally filtered by ticker and/or older than a date."""
        sql = "DELETE FROM orders"
        params: list = []
        conditions: list[str] = []
        if ticker:
            conditions.append("ticker = ?")
            params.append(ticker)
        if before_date:
            conditions.append("created_at < ?")
            params.append(before_date)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        with self._connect() as conn:
            cursor = conn.execute(sql, params)
            return cursor.rowcount

    def get_audit_logs(
        self,
        event_type: str | None = None,
        actor: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Read audit log entries with optional filtering and pagination."""
        sql = "SELECT * FROM audit_log"
        params: list = []
        conditions: list[str] = []
        if event_type:
            conditions.append("event_type LIKE ?")
            params.append(f"{event_type}%")
        if actor:
            conditions.append("actor = ?")
            params.append(actor)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY rowid DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self._connect() as conn:
            cursor = conn.execute(sql, params)
            cols = [d[0] for d in cursor.description]
            rows = cursor.fetchall()
            return [dict(zip(cols, row)) for row in rows]

    def delete_audit_logs(self, before_date: str | None = None, event_type: str | None = None) -> int:
        """Delete audit logs, optionally filtered by date and/or event_type prefix."""
        sql = "DELETE FROM audit_log"
        params: list = []
        conditions: list[str] = []
        if before_date:
            conditions.append("timestamp < ?")
            params.append(before_date)
        if event_type:
            conditions.append("event_type LIKE ?")
            params.append(f"{event_type}%")
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        with self._connect() as conn:
            cursor = conn.execute(sql, params)
            return cursor.rowcount

    def delete_position(self, position_id: int) -> bool:
        """Delete a position by ID. Returns True if deleted."""
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM positions WHERE id = ?", (position_id,))
            return cursor.rowcount > 0

    def delete_ai_weights(self, ticker: str | None = None, before_date: str | None = None) -> int:
        """Delete AI weight entries, optionally filtered by ticker and/or date."""
        sql = "DELETE FROM ai_weights"
        params: list = []
        conditions: list[str] = []
        if ticker:
            conditions.append("ticker = ?")
            params.append(ticker)
        if before_date:
            conditions.append("created_at < ?")
            params.append(before_date)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        with self._connect() as conn:
            cursor = conn.execute(sql, params)
            return cursor.rowcount

    def delete_equity_snapshots(self, before_date: str | None = None) -> int:
        """Delete equity snapshots, optionally older than a date."""
        sql = "DELETE FROM equity_snapshots"
        params: list = []
        if before_date:
            sql += " WHERE date < ?"
            params.append(before_date)
        with self._connect() as conn:
            cursor = conn.execute(sql, params)
            return cursor.rowcount

    def delete_daily_risk_metrics(self, before_date: str | None = None) -> int:
        """Delete daily risk metrics, optionally older than a date."""
        sql = "DELETE FROM daily_risk_metrics"
        params: list = []
        if before_date:
            sql += " WHERE date < ?"
            params.append(before_date)
        with self._connect() as conn:
            cursor = conn.execute(sql, params)
            return cursor.rowcount

    def delete_relationships(self, asset_a: str | None = None) -> int:
        """Delete relationship matrix entries, optionally filtered by asset_a."""
        sql = "DELETE FROM relationship_matrix"
        params: list = []
        if asset_a:
            sql += " WHERE asset_a = ?"
            params.append(asset_a)
        with self._connect() as conn:
            cursor = conn.execute(sql, params)
            return cursor.rowcount

    def delete_corporate_actions(self, ticker: str) -> int:
        """Delete corporate actions for a ticker."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM corporate_actions WHERE ticker = ?", (ticker,)
            )
            return cursor.rowcount

    def delete_news(self, source: str | None = None, before_date: str | None = None) -> int:
        """Delete news entries, optionally filtered by source and/or date."""
        sql = "DELETE FROM news"
        params: list = []
        conditions: list[str] = []
        if source:
            conditions.append("source = ?")
            params.append(source)
        if before_date:
            conditions.append("published_at < ?")
            params.append(before_date)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        with self._connect() as conn:
            cursor = conn.execute(sql, params)
            return cursor.rowcount

    # ---------- D1: Instrument Master ----------
    def save_instrument_master(self, record: dict):
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO instrument_master
                   (ticker, name, sector, subsector, exchange, listing_date,
                    delisting_date, is_active, board, market_cap, free_float,
                    asset_class, updated_at, ipo_date, ipo_price, status,
                    lock_up_end_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(ticker) DO UPDATE SET
                     name = COALESCE(excluded.name, instrument_master.name),
                     sector = COALESCE(excluded.sector, instrument_master.sector),
                     subsector = COALESCE(excluded.subsector, instrument_master.subsector),
                     exchange = COALESCE(excluded.exchange, instrument_master.exchange),
                     listing_date = COALESCE(excluded.listing_date, instrument_master.listing_date),
                     delisting_date = COALESCE(excluded.delisting_date, instrument_master.delisting_date),
                     is_active = COALESCE(excluded.is_active, instrument_master.is_active),
                     board = COALESCE(excluded.board, instrument_master.board),
                     market_cap = COALESCE(excluded.market_cap, instrument_master.market_cap),
                     free_float = COALESCE(excluded.free_float, instrument_master.free_float),
                     asset_class = COALESCE(excluded.asset_class, instrument_master.asset_class),
                     ipo_date = COALESCE(excluded.ipo_date, instrument_master.ipo_date),
                     ipo_price = COALESCE(excluded.ipo_price, instrument_master.ipo_price),
                     status = COALESCE(excluded.status, instrument_master.status),
                     lock_up_end_date = COALESCE(excluded.lock_up_end_date, instrument_master.lock_up_end_date),
                     updated_at = excluded.updated_at""",
                (
                    record.get("ticker"),
                    record.get("name"),
                    record.get("sector"),
                    record.get("subsector"),
                    record.get("exchange", "IDX"),
                    record.get("listing_date"),
                    record.get("delisting_date"),
                    record.get("is_active", 1),
                    record.get("board"),
                    record.get("market_cap"),
                    record.get("free_float"),
                    record.get("asset_class", "equity"),
                    datetime.now(UTC).isoformat(),
                    record.get("ipo_date"),
                    record.get("ipo_price"),
                    record.get("status", "active"),
                    record.get("lock_up_end_date"),
                ),
            )
        # Auto-sync to Parquet
        self._sync_table_to_parquet("instrument_master")

    def load_instrument_master_tickers(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT ticker FROM instrument_master").fetchall()
            return [r[0] for r in rows]

    def load_idx_stock_tickers(self, active_only: bool = True) -> list[str]:
        """Return tickers for IDX stocks (asset_class='equity'), optionally active only."""
        with self._connect() as conn:
            if active_only:
                rows = conn.execute(
                    "SELECT ticker FROM instrument_master WHERE asset_class = 'equity' AND (is_active = 1 OR is_active IS NULL)"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT ticker FROM instrument_master WHERE asset_class = 'equity'"
                ).fetchall()
            return [r[0] for r in rows]

    def load_non_equity_tickers(self) -> list[dict]:
        """Return non-equity tickers (indices, commodities, forex, etfs) for relationship analysis."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT ticker, name, asset_class, exchange FROM instrument_master WHERE asset_class != 'equity'"
            ).fetchall()
            return [{"ticker": r[0], "name": r[1], "asset_class": r[2], "exchange": r[3]} for r in rows]

    def get_instrument_status(self, ticker: str) -> dict | None:
        """Return instrument lifecycle metadata for a ticker.

        Keys: ticker, listing_date, delisting_date, ipo_date, ipo_price,
        status, lock_up_end_date, is_active.
        """
        with self._connect() as conn:
            row = conn.execute(
                """SELECT ticker, listing_date, delisting_date, ipo_date,
                          ipo_price, status, lock_up_end_date, is_active
                   FROM instrument_master WHERE ticker = ?""",
                (ticker,),
            ).fetchone()
            if not row:
                return None
            return {
                "ticker": row[0],
                "listing_date": row[1],
                "delisting_date": row[2],
                "ipo_date": row[3],
                "ipo_price": row[4],
                "status": row[5] or "active",
                "lock_up_end_date": row[6],
                "is_active": row[7],
            }

    def is_tradeable(self, ticker: str, as_of: str | None = None) -> bool:
        """Check if a ticker was tradeable on a given date (or today).

        Returns False if:
        - status is 'suspended' or 'delisted'
        - as_of is before listing_date / ipo_date
        - as_of is after delisting_date
        - as_of is within a suspension period
        """
        from datetime import datetime as _dt

        info = self.get_instrument_status(ticker)
        if info is None:
            return True  # Unknown ticker — allow by default

        check_date = as_of or _dt.now(UTC).strftime("%Y-%m-%d")

        # Status check: 'suspended' always blocks (currently suspended).
        # 'delisted' only blocks if we're checking at/after the delisting date.
        if info["status"] == "suspended":
            return False
        if info["status"] == "delisted":
            delisting = info.get("delisting_date")
            if delisting is None or check_date >= delisting:
                return False

        listing = info.get("listing_date") or info.get("ipo_date")
        if listing and check_date < listing:
            return False

        delisting = info.get("delisting_date")
        if delisting and check_date >= delisting:
            return False

        suspensions = self.load_suspensions(ticker)
        for s in suspensions:
            s_start = s.get("suspend_date")
            s_end = s.get("resume_date")
            if s_start and check_date >= s_start:
                if s_end is None or check_date < s_end:
                    return False

        return True

    def load_active_tickers_at_date(self, as_of: str, exchange: str = "IDX") -> list[str]:
        """Return tickers that were actively listed on a given date.

        Used for survivorship-bias-free backtests: only includes tickers
        whose listing_date <= as_of and (delisting_date IS NULL or delisting_date > as_of).
        """
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT ticker FROM instrument_master
                   WHERE asset_class = 'equity'
                     AND (listing_date IS NULL OR listing_date <= ?)
                     AND (delisting_date IS NULL OR delisting_date > ?)
                     AND (status IS NULL OR status NOT IN ('delisted'))
                   ORDER BY ticker""",
                (as_of, as_of),
            ).fetchall()
            return [r[0] for r in rows]

    # ---------- Trading Suspensions ----------
    def save_suspension(self, record: dict):
        """Insert a trading suspension record."""
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO trading_suspensions
                   (ticker, suspend_date, resume_date, reason, suspension_type, source, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.get("ticker"),
                    record.get("suspend_date"),
                    record.get("resume_date"),
                    record.get("reason"),
                    record.get("suspension_type"),
                    record.get("source", "manual"),
                    datetime.now(UTC).isoformat(),
                ),
            )
        # Auto-sync to Parquet
        self._sync_table_to_parquet("trading_suspensions")

    def load_suspensions(self, ticker: str | None = None) -> list[dict]:
        """Load suspension records, optionally filtered by ticker."""
        with self._connect() as conn:
            if ticker:
                rows = conn.execute(
                    "SELECT * FROM trading_suspensions WHERE ticker = ? ORDER BY suspend_date DESC",
                    (ticker,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM trading_suspensions ORDER BY suspend_date DESC"
                ).fetchall()
            cols = [d[0] for d in conn.execute("SELECT * FROM trading_suspensions LIMIT 0").description]
            return [dict(zip(cols, row)) for row in rows]

    def load_active_suspensions(self, as_of: str | None = None) -> list[dict]:
        """Load suspensions that are active on a given date (resume_date is NULL or > as_of)."""
        from datetime import datetime as _dt
        check_date = as_of or _dt.now(UTC).strftime("%Y-%m-%d")
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM trading_suspensions
                   WHERE suspend_date <= ?
                     AND (resume_date IS NULL OR resume_date > ?)
                   ORDER BY suspend_date DESC""",
                (check_date, check_date),
            ).fetchall()
            cols = [d[0] for d in conn.execute("SELECT * FROM trading_suspensions LIMIT 0").description]
            return [dict(zip(cols, row)) for row in rows]

    # ---------- D31: Pattern Analysis ----------
    def save_pattern_analysis(self, record: dict):
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO pattern_analysis
                   (ticker, date, pattern_type, confidence, direction, details, source, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.get("ticker"),
                    record.get("date"),
                    record.get("pattern_type"),
                    record.get("confidence"),
                    record.get("direction"),
                    record.get("details"),
                    record.get("source", "technical"),
                    datetime.now(UTC).isoformat(),
                ),
            )

    # ---------- D2: Fundamental Data ----------
    def save_fundamental(self, record: dict):
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO fundamental_data
                   (ticker, date, pe_ratio, pb_ratio, roe, debt_to_equity,
                    dividend_yield, earnings_per_share, book_value_per_share,
                    net_profit, revenue, total_assets, total_liabilities,
                    cash_flow, fiscal_year, quarter, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(ticker, date) DO UPDATE SET
                     pe_ratio = COALESCE(excluded.pe_ratio, fundamental_data.pe_ratio),
                     pb_ratio = COALESCE(excluded.pb_ratio, fundamental_data.pb_ratio),
                     roe = COALESCE(excluded.roe, fundamental_data.roe),
                     debt_to_equity = COALESCE(excluded.debt_to_equity, fundamental_data.debt_to_equity),
                     dividend_yield = COALESCE(excluded.dividend_yield, fundamental_data.dividend_yield),
                     earnings_per_share = COALESCE(excluded.earnings_per_share, fundamental_data.earnings_per_share),
                     book_value_per_share = COALESCE(excluded.book_value_per_share, fundamental_data.book_value_per_share),
                     net_profit = COALESCE(excluded.net_profit, fundamental_data.net_profit),
                     revenue = COALESCE(excluded.revenue, fundamental_data.revenue),
                     total_assets = COALESCE(excluded.total_assets, fundamental_data.total_assets),
                     total_liabilities = COALESCE(excluded.total_liabilities, fundamental_data.total_liabilities),
                     cash_flow = COALESCE(excluded.cash_flow, fundamental_data.cash_flow),
                     fiscal_year = COALESCE(excluded.fiscal_year, fundamental_data.fiscal_year),
                     quarter = COALESCE(excluded.quarter, fundamental_data.quarter),
                     source = COALESCE(excluded.source, fundamental_data.source)""",
                (
                    record.get("ticker"),
                    record.get("date") or record.get("as_of"),
                    record.get("pe_ratio"),
                    record.get("pb_ratio"),
                    record.get("roe"),
                    record.get("debt_to_equity"),
                    record.get("dividend_yield"),
                    record.get("earnings_per_share"),
                    record.get("book_value_per_share"),
                    record.get("net_profit"),
                    record.get("revenue"),
                    record.get("total_assets"),
                    record.get("total_liabilities"),
                    record.get("cash_flow"),
                    record.get("fiscal_year"),
                    record.get("quarter"),
                    record.get("source", "yfinance"),
                ),
            )

    # ---------- D4: Foreign Flow ----------
    def save_foreign_flow(self, record: dict):
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO foreign_flow
                   (ticker, date, foreign_buy, foreign_sell, foreign_net,
                    domestic_buy, domestic_sell, domestic_net, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.get("ticker") or record.get("kode"),
                    record.get("date") or record.get("tanggal"),
                    record.get("foreign_buy"),
                    record.get("foreign_sell"),
                    record.get("foreign_net"),
                    record.get("domestic_buy"),
                    record.get("domestic_sell"),
                    record.get("domestic_net"),
                    record.get("source", "idx_scraper"),
                ),
            )

    def load_foreign_flow(
        self,
        ticker: str,
        start: str | None = None,
        end: str | None = None,
        source: str = "idx_scraper",
    ) -> pd.DataFrame:
        """Load foreign flow data for a ticker from the foreign_flow table.

        Args:
            ticker: Stock code (without .JK suffix, e.g. 'BBCA').
            start: Optional start date (YYYY-MM-DD).
            end: Optional end date (YYYY-MM-DD).
            source: Filter by source. Default 'idx_scraper' (real IDX data).
                    Pass None to load all sources.

        Returns:
            DataFrame sorted by date ascending with columns:
            ticker, date, foreign_buy, foreign_sell, foreign_net,
            domestic_buy, domestic_sell, domestic_net, source.
        """
        sql = "SELECT * FROM foreign_flow WHERE ticker = ?"
        params: list = [ticker]
        if source is not None:
            sql += " AND source = ?"
            params.append(source)
        if start:
            sql += " AND date >= ?"
            params.append(start)
        if end:
            sql += " AND date <= ?"
            params.append(end)
        sql += " ORDER BY date"
        with self._connect() as conn:
            return pd.read_sql_query(sql, conn, params=params)

    def load_broker_flow(
        self,
        date: str | None = None,
        source: str = "idx_scraper",
    ) -> pd.DataFrame:
        """Load broker flow data (market-wide aggregate per broker per day).

        Args:
            date: Optional date filter (YYYY-MM-DD). None = all dates.
            source: Filter by source. Default 'idx_scraper'.

        Returns:
            DataFrame sorted by date, broker.
        """
        sql = "SELECT * FROM broker_flow WHERE 1=1"
        params: list = []
        if source is not None:
            sql += " AND source = ?"
            params.append(source)
        if date:
            sql += " AND date = ?"
            params.append(date)
        sql += " ORDER BY date, net_value DESC"
        with self._connect() as conn:
            return pd.read_sql_query(sql, conn, params=params)

    # ---------- D5: Broker Flow ----------
    def save_broker_flow(self, record: dict):
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO broker_flow
                   (ticker, date, broker, buy_volume, buy_value, sell_volume,
                    sell_value, net_volume, net_value, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.get("ticker"),
                    record.get("date"),
                    record.get("broker"),
                    record.get("buy_volume"),
                    record.get("buy_value"),
                    record.get("sell_volume"),
                    record.get("sell_value"),
                    record.get("net_volume"),
                    record.get("net_value"),
                    record.get("source", "idx_scraper"),
                ),
            )

    # ---------- D7: Dividends ----------
    def save_dividend(self, record: dict):
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO dividends
                   (ticker, ex_date, record_date, payment_date, amount,
                    currency, frequency, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.get("ticker"),
                    record.get("ex_date"),
                    record.get("record_date"),
                    record.get("payment_date"),
                    record.get("amount") or record.get("value"),
                    record.get("currency", "IDR"),
                    record.get("frequency"),
                    record.get("source", "yfinance"),
                ),
            )

    # ---------- D18: Technical Indicators ----------
    def save_technical_indicator(self, record: dict):
        """Save a single technical indicator row (long format)."""
        indicator_map = {
            "ma_20": "MA20", "ma_50": "MA50", "rsi": "RSI",
            "macd": "MACD", "macd_signal": "MACD_SIGNAL",
            "adx": "ADX", "atr_14": "ATR14",
            "bb_upper": "BB_UPPER", "bb_lower": "BB_LOWER",
            "volume_sma_20": "VOLUME_SMA20", "volume_ratio": "VOLUME_RATIO",
            "volatility_20": "VOLATILITY_20",
        }
        ticker = record.get("ticker")
        raw_date = record.get("timestamp") or record.get("date")
        # Normalize date to YYYY-MM-DD (strip time component if present)
        if raw_date and isinstance(raw_date, str) and len(raw_date) > 10:
            raw_date = raw_date[:10]
        date = raw_date
        source = record.get("source", "computed")
        with self._connect() as conn:
            for key, indicator_name in indicator_map.items():
                val = record.get(key)
                if val is not None and not (isinstance(val, float) and val != val):
                    conn.execute(
                        """INSERT OR REPLACE INTO technical_indicators
                           (ticker, date, indicator, value, timeframe, source)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (ticker, date, indicator_name, float(val), "1d", source),
                    )

    # ---------- News ----------
    def save_news(self, record: dict):
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO news
                   (news_id, headline, body, published_at, source,
                    entities, topic, sentiment, impact)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.get("news_id"),
                    record.get("headline"),
                    record.get("body"),
                    record.get("published_at"),
                    record.get("source"),
                    record.get("entities"),
                    record.get("topic"),
                    record.get("sentiment"),
                    record.get("impact"),
                ),
            )

    # ---------- Sector Master ----------
    def save_sector(self, record: dict):
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO sector_master
                   (kode, nama, deskripsi, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    record.get("kode") or record.get("sector_code"),
                    record.get("nama") or record.get("sector_name"),
                    record.get("deskripsi") or record.get("description"),
                    datetime.now(UTC).isoformat(),
                    datetime.now(UTC).isoformat(),
                ),
            )

    # ---------- Market Calendar ----------
    def save_market_calendar(self, record: dict):
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO market_calendar
                   (date, exchange, is_trading_day, holiday_name, half_day, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    record.get("date"),
                    record.get("exchange", "IDX"),
                    record.get("is_trading_day", 1),
                    record.get("holiday_name"),
                    record.get("half_day", 0),
                    datetime.now(UTC).isoformat(),
                ),
            )

    # ---------- Fear & Greed ----------
    def save_fear_greed(self, record: dict):
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO fear_greed
                   (tanggal, nilai, label, created_at)
                   VALUES (?, ?, ?, ?)""",
                (
                    record.get("tanggal") or record.get("date"),
                    int(record.get("nilai", record.get("value", 50))),
                    record.get("label") or record.get("classification"),
                    datetime.now(UTC).isoformat(),
                ),
            )

    # ---------- External Events ----------
    def save_external_event(self, record: dict):
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO external_events
                   (tanggal, kategori, judul, lokasi, dampak_market, sektor, deskripsi, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.get("tanggal") or record.get("date"),
                    record.get("kategori") or record.get("event_type"),
                    record.get("judul") or record.get("description"),
                    record.get("lokasi") or record.get("region", "ID"),
                    record.get("dampak_market") or record.get("impact_level"),
                    record.get("sektor", ""),
                    record.get("deskripsi", ""),
                    datetime.now(UTC).isoformat(),
                ),
            )

    # ---------- ESG Scores ----------
    def save_esg_score(self, record: dict):
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO esg_scores
                   (kode, year, rating_agency, rating, score, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    record.get("kode") or record.get("ticker", ""),
                    record.get("year") or int(datetime.now(UTC).year),
                    record.get("rating_agency", "yfinance"),
                    record.get("rating"),
                    record.get("score") or record.get("esg_score"),
                    datetime.now(UTC).isoformat(),
                ),
            )

    # ---------- Corporate Governance ----------
    def save_corporate_governance(self, record: dict):
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO corporate_governance
                   (kode, year, board_commissioners, independent_commissioners,
                    board_directors, audit_committee_meetings, gcg_score, acgs_score,
                    has_whistleblowing, has_risk_committee, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.get("kode") or record.get("ticker", ""),
                    record.get("year") or int(datetime.now(UTC).year),
                    record.get("board_commissioners") or record.get("board_size"),
                    record.get("independent_commissioners") or record.get("independent_directors"),
                    record.get("board_directors"),
                    record.get("audit_committee_meetings"),
                    record.get("gcg_score"),
                    record.get("acgs_score"),
                    record.get("has_whistleblowing"),
                    record.get("has_risk_committee"),
                    datetime.now(UTC).isoformat(),
                ),
            )

    # ---------- Stock Personality ----------
    def save_stock_personality(self, record: dict):
        # Map string liquidity profile to numeric score
        liq_str = record.get("liquidity_score") or record.get("liquidity_profile", "")
        liq_map = {"high_liquidity": 1.0, "moderate_liquidity": 0.5, "low_liquidity": 0.2}
        liq_numeric = liq_map.get(liq_str, 0.5)
        if isinstance(liq_str, (int, float)):
            liq_numeric = float(liq_str)

        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO stock_personality
                   (kode, profile_date, avg_daily_volatility, volatility_regime,
                    trend_bias, trend_strength, beta_vs_ihsg, correlation_ihsg,
                    avg_volume, liquidity_score, personality_label, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.get("kode") or record.get("ticker", ""),
                    record.get("profile_date") or datetime.now(UTC).strftime("%Y-%m-%d"),
                    record.get("avg_daily_volatility"),
                    record.get("volatility_regime") or record.get("volatility_profile"),
                    record.get("trend_bias"),
                    record.get("trend_strength"),
                    record.get("beta_vs_ihsg") or record.get("beta"),
                    record.get("correlation_ihsg") or record.get("correlation_to_ihsg"),
                    record.get("avg_volume"),
                    liq_numeric,
                    record.get("personality_label") or record.get("personality_type"),
                    datetime.now(UTC).isoformat(),
                ),
            )

    # ---------- Macro Data ----------
    def save_macro_data(self, record: dict):
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO macro_data
                   (series_name, date, value, unit, source, frequency)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    record.get("series_name"),
                    record.get("date"),
                    record.get("value"),
                    record.get("unit"),
                    record.get("source"),
                    record.get("frequency", "daily"),
                ),
            )
