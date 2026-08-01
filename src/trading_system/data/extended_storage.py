"""Extended Storage: query methods for 14 new tables imported from MySQL.

Tables covered:
  saham_snapshot, shareholders, company_directors, broker_summary,
  pattern_reliability, pattern_candidates, advanced_features, ai_scores_history,
  idx_sentiment_data, idx_market_indices, idx_financial_statements,
  idx_social_media_sentiment, idx_stock_splits, idx_quarterly_earnings
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

import pandas as pd

from trading_system.config import DB_PATH


class ExtendedStorage:
    """Read-only accessors for legacy/imported tables."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = str(db_path or DB_PATH)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ──────────────────────────────────────────────
    # saham_snapshot — daily price + valuation snapshot
    # ──────────────────────────────────────────────
    def get_snapshots(
        self, kode: str | None = None, start: str | None = None, end: str | None = None
    ) -> pd.DataFrame:
        sql = "SELECT * FROM saham_snapshot WHERE 1=1"
        params: list[Any] = []
        if kode:
            sql += " AND kode = ?"
            params.append(kode)
        if start:
            sql += " AND tanggal >= ?"
            params.append(start)
        if end:
            sql += " AND tanggal <= ?"
            params.append(end)
        sql += " ORDER BY tanggal"
        with self._connect() as conn:
            return pd.read_sql_query(sql, conn, params=params)

    def get_latest_snapshot(self, kode: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM saham_snapshot WHERE kode = ? ORDER BY tanggal DESC LIMIT 1",
                (kode,),
            ).fetchone()
        return dict(row) if row else None

    # ──────────────────────────────────────────────
    # shareholders
    # ──────────────────────────────────────────────
    def get_shareholders(self, kode: str) -> pd.DataFrame:
        with self._connect() as conn:
            return pd.read_sql_query(
                "SELECT * FROM shareholders WHERE kode = ? ORDER BY persentase DESC",
                conn,
                params=[kode],
            )

    # ──────────────────────────────────────────────
    # company_directors
    # ──────────────────────────────────────────────
    def get_directors(self, kode: str) -> pd.DataFrame:
        with self._connect() as conn:
            return pd.read_sql_query(
                "SELECT * FROM company_directors WHERE kode = ? ORDER BY tipe, nama",
                conn,
                params=[kode],
            )

    # ──────────────────────────────────────────────
    # broker_summary
    # ──────────────────────────────────────────────
    def get_broker_summary(self, tanggal: str | None = None, limit: int = 50) -> pd.DataFrame:
        sql = "SELECT * FROM broker_summary"
        params: list[Any] = []
        if tanggal:
            sql += " WHERE tanggal = ?"
            params.append(tanggal)
        sql += " ORDER BY value DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            return pd.read_sql_query(sql, conn, params=params)

    # ──────────────────────────────────────────────
    # pattern_reliability
    # ──────────────────────────────────────────────
    def get_pattern_reliability(
        self, kode: str | None = None, min_rating: str | None = None
    ) -> pd.DataFrame:
        sql = "SELECT * FROM pattern_reliability WHERE 1=1"
        params: list[Any] = []
        if kode:
            sql += " AND kode = ?"
            params.append(kode)
        rating_order = {"excellent": 5, "good": 4, "average": 3, "poor": 2, "avoid": 1}
        if min_rating and min_rating in rating_order:
            threshold = rating_order[min_rating]
            allowed = [k for k, v in rating_order.items() if v >= threshold]
            placeholders = ",".join(["?" for _ in allowed])
            sql += f" AND reliability_rating IN ({placeholders})"
            params.extend(allowed)
        sql += " ORDER BY win_rate DESC"
        with self._connect() as conn:
            return pd.read_sql_query(sql, conn, params=params)

    # ──────────────────────────────────────────────
    # pattern_candidates
    # ──────────────────────────────────────────────
    def get_pattern_candidates(
        self, kode: str | None = None, status: str = "candidate"
    ) -> pd.DataFrame:
        sql = "SELECT * FROM pattern_candidates WHERE status = ?"
        params: list[Any] = [status]
        if kode:
            sql += " AND kode = ?"
            params.append(kode)
        sql += " ORDER BY preliminary_score DESC"
        with self._connect() as conn:
            return pd.read_sql_query(sql, conn, params=params)

    # ──────────────────────────────────────────────
    # advanced_features (JSON columns)
    # ──────────────────────────────────────────────
    def get_advanced_features(self, kode: str | None = None) -> pd.DataFrame:
        sql = "SELECT * FROM advanced_features"
        params: list[Any] = []
        if kode:
            sql += " WHERE kode = ?"
            params.append(kode)
        sql += " ORDER BY advanced_score DESC"
        with self._connect() as conn:
            return pd.read_sql_query(sql, conn, params=params)

    def get_advanced_features_parsed(self, kode: str) -> dict:
        """Return advanced features with JSON columns parsed."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM advanced_features WHERE kode = ? ORDER BY created_at DESC LIMIT 1",
                (kode,),
            ).fetchone()
        if not row:
            return {}
        result = dict(row)
        for key in ("order_flow", "volume_profile", "price_anomaly", "volume_anomaly",
                     "market_regime", "volatility_regime"):
            if result.get(key):
                try:
                    result[key] = json.loads(result[key])
                except (json.JSONDecodeError, TypeError):
                    pass
        return result

    # ──────────────────────────────────────────────
    # ai_scores_history
    # ──────────────────────────────────────────────
    def get_ai_scores_history(
        self, kode: str | None = None, start: str | None = None, end: str | None = None
    ) -> pd.DataFrame:
        sql = "SELECT * FROM ai_scores_history WHERE 1=1"
        params: list[Any] = []
        if kode:
            sql += " AND kode = ?"
            params.append(kode)
        if start:
            sql += " AND tanggal >= ?"
            params.append(start)
        if end:
            sql += " AND tanggal <= ?"
            params.append(end)
        sql += " ORDER BY tanggal"
        with self._connect() as conn:
            return pd.read_sql_query(sql, conn, params=params)

    # ──────────────────────────────────────────────
    # idx_sentiment_data
    # ──────────────────────────────────────────────
    def get_sentiment(
        self, symbol: str | None = None, start: str | None = None, end: str | None = None
    ) -> pd.DataFrame:
        sql = "SELECT * FROM idx_sentiment_data WHERE 1=1"
        params: list[Any] = []
        if symbol:
            sql += " AND symbol = ?"
            params.append(symbol)
        if start:
            sql += " AND date >= ?"
            params.append(start)
        if end:
            sql += " AND date <= ?"
            params.append(end)
        sql += " ORDER BY date"
        with self._connect() as conn:
            return pd.read_sql_query(sql, conn, params=params)

    def get_latest_sentiment(self, symbol: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM idx_sentiment_data WHERE symbol = ? ORDER BY date DESC LIMIT 1",
                (symbol,),
            ).fetchone()
        return dict(row) if row else None

    # ──────────────────────────────────────────────
    # idx_market_indices
    # ──────────────────────────────────────────────
    def get_market_indices(
        self, index_name: str | None = None, start: str | None = None, end: str | None = None
    ) -> pd.DataFrame:
        sql = "SELECT * FROM idx_market_indices WHERE 1=1"
        params: list[Any] = []
        if index_name:
            sql += " AND index_name = ?"
            params.append(index_name)
        if start:
            sql += " AND date >= ?"
            params.append(start)
        if end:
            sql += " AND date <= ?"
            params.append(end)
        sql += " ORDER BY date"
        with self._connect() as conn:
            return pd.read_sql_query(sql, conn, params=params)

    # ──────────────────────────────────────────────
    # idx_financial_statements
    # ──────────────────────────────────────────────
    def get_financial_statements(
        self, symbol: str | None = None, period_type: str | None = None
    ) -> pd.DataFrame:
        sql = "SELECT * FROM idx_financial_statements WHERE 1=1"
        params: list[Any] = []
        if symbol:
            sql += " AND symbol = ?"
            params.append(symbol)
        if period_type:
            sql += " AND period_type = ?"
            params.append(period_type)
        sql += " ORDER BY period_date DESC"
        with self._connect() as conn:
            return pd.read_sql_query(sql, conn, params=params)

    # ──────────────────────────────────────────────
    # idx_social_media_sentiment
    # ──────────────────────────────────────────────
    def get_social_media_sentiment(
        self, symbol: str | None = None, platform: str | None = None, limit: int = 100
    ) -> pd.DataFrame:
        sql = "SELECT * FROM idx_social_media_sentiment WHERE 1=1"
        params: list[Any] = []
        if symbol:
            sql += " AND symbol = ?"
            params.append(symbol)
        if platform:
            sql += " AND platform = ?"
            params.append(platform)
        sql += " ORDER BY posted_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            return pd.read_sql_query(sql, conn, params=params)

    # ──────────────────────────────────────────────
    # idx_stock_splits
    # ──────────────────────────────────────────────
    def get_stock_splits(self, symbol: str | None = None) -> pd.DataFrame:
        sql = "SELECT * FROM idx_stock_splits"
        params: list[Any] = []
        if symbol:
            sql += " WHERE symbol = ?"
            params.append(symbol)
        sql += " ORDER BY date DESC"
        with self._connect() as conn:
            return pd.read_sql_query(sql, conn, params=params)

    # ──────────────────────────────────────────────
    # idx_quarterly_earnings
    # ──────────────────────────────────────────────
    def get_quarterly_earnings(self, symbol: str | None = None) -> pd.DataFrame:
        sql = "SELECT * FROM idx_quarterly_earnings"
        params: list[Any] = []
        if symbol:
            sql += " WHERE symbol = ?"
            params.append(symbol)
        sql += " ORDER BY quarter_date DESC"
        with self._connect() as conn:
            return pd.read_sql_query(sql, conn, params=params)
