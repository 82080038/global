"""Data Storage menggunakan SQLite (Phase 1).

Nantinya dapat diganti TimescaleDB/InfluxDB tanpa mengubah kontrak fungsi.
"""

import sqlite3
from contextlib import contextmanager
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
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    # ---------- Scores ----------
    def save_score(self, ticker: str, engine: str, score: float, breakdown: dict, as_of: str | None = None):
        import json
        from datetime import datetime, timezone

        if as_of is None:
            as_of = datetime.now(timezone.utc).isoformat()
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
        from datetime import datetime, timezone

        if updated_at is None:
            updated_at = datetime.now(timezone.utc).isoformat()
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
        with self._connect() as conn:
            df = df.copy()
            for col in ["ingested_at"]:
                if col not in df.columns:
                    df[col] = None
            for _, row in df.iterrows():
                conn.execute(
                    """
                    INSERT OR REPLACE INTO ohlcv
                    (ticker, asset_class, exchange, timestamp, timeframe, open, high, low,
                     close, volume, adjusted_close, source, ingested_at, data_quality_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row.get("ticker"), row.get("asset_class", "equity"),
                        row.get("exchange", "IDX"), row.get("timestamp"),
                        row.get("timeframe", "1d"), float(row.get("open")),
                        float(row.get("high")), float(row.get("low")),
                        float(row.get("close")), float(row.get("volume")),
                        float(row.get("close")),  # adjusted_close sementara sama close (belum aksi korporasi)
                        row.get("source"), row.get("ingested_at"),
                        row.get("data_quality_score"),
                    ),
                )
        return len(df)

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
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
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
        from datetime import datetime, timezone

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO audit_log (event_type, payload, timestamp, actor) VALUES (?, ?, ?, ?)",
                (event_type, json.dumps(payload, default=str), datetime.now(timezone.utc).isoformat(), actor),
            )

    # ---------- Positions ----------
    def save_position(self, ticker: str, quantity: float, avg_entry_price: float,
                      stop_loss: float | None = None, take_profit: float | None = None,
                      trailing_stop_pct: float = 0.05) -> int:
        """Create a new position. Returns position id."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
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
        from datetime import datetime, timezone
        if "closed_at" not in kwargs and kwargs.get("status") == "CLOSED":
            kwargs["closed_at"] = datetime.now(timezone.utc).isoformat()
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
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
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
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
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
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        today = datetime.now(timezone.utc).date().isoformat()
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
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
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
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc).isoformat()
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
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
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
        from datetime import datetime, timezone, timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
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
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        today = datetime.now(timezone.utc).date().isoformat()
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
