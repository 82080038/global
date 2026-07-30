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
        import json
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
