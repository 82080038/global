"""Data Storage menggunakan SQLite (Phase 1).

Nantinya dapat diganti TimescaleDB/InfluxDB tanpa mengubah kontrak fungsi.
"""

import sqlite3
from contextlib import contextmanager
from datetime import UTC
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
    free_float REAL, updated_at TEXT
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
    sector_code TEXT PRIMARY KEY, sector_name TEXT, parent_sector TEXT,
    description TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS market_calendar (
    date TEXT PRIMARY KEY, exchange TEXT, is_trading_day INTEGER DEFAULT 1,
    holiday_name TEXT, half_day INTEGER DEFAULT 0, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS fear_greed (
    date TEXT PRIMARY KEY, value REAL, classification TEXT,
    source TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS external_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, event_type TEXT,
    description TEXT, region TEXT, impact_level TEXT, source TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS esg_scores (
    ticker TEXT, date TEXT, e_score REAL, s_score REAL, g_score REAL,
    esg_score REAL, source TEXT, PRIMARY KEY (ticker, date, source)
);
CREATE TABLE IF NOT EXISTS corporate_governance (
    ticker TEXT, date TEXT, board_size INTEGER, independent_directors INTEGER,
    audit_committee_quality TEXT, ownership_concentration REAL, source TEXT,
    PRIMARY KEY (ticker, date, source)
);
CREATE TABLE IF NOT EXISTS stock_personality (
    ticker TEXT PRIMARY KEY, personality_type TEXT, volatility_profile TEXT,
    liquidity_profile TEXT, beta REAL, correlation_to_ihsg REAL, updated_at TEXT
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
        return len(df)

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
        sql += " ORDER BY timestamp"
        with self._connect() as conn:
            df = pd.read_sql_query(sql, conn, params=params)
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
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

    def update_position(self, position_id: int, **kwargs):
        """Update position fields."""
        from datetime import datetime
        if "closed_at" not in kwargs and kwargs.get("status") == "CLOSED":
            kwargs["closed_at"] = datetime.now(UTC).isoformat()
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
