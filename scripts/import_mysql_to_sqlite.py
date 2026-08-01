"""Import tabel unik dari MySQL (data_pasar_modal & idx_complete_data) ke SQLite.

Hanya tabel yang BELUM ada di SQLite trading-system yang di-import.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pymysql

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "trading_system.db"

MYSQL_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "root",
    "unix_socket": "/opt/lampp/var/mysql/mysql.sock",
    "charset": "utf8mb4",
}

# Tabel yang akan di-import: (mysql_db, mysql_table, sqlite_table, create_sql)
IMPORT_LIST = [
    # === data_pasar_modal ===
    ("data_pasar_modal", "saham_snapshot", "saham_snapshot", """
        CREATE TABLE IF NOT EXISTS saham_snapshot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kode TEXT NOT NULL,
            tanggal TEXT NOT NULL,
            harga REAL DEFAULT 0,
            perubahan REAL DEFAULT 0,
            volume REAL DEFAULT 0,
            per REAL DEFAULT 0,
            pbv REAL DEFAULT 0,
            roe REAL,
            der REAL,
            market_cap REAL,
            created_at TEXT,
            UNIQUE(kode, tanggal)
        )
    """),
    ("data_pasar_modal", "shareholders", "shareholders", """
        CREATE TABLE IF NOT EXISTS shareholders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kode TEXT NOT NULL,
            nama TEXT NOT NULL,
            jumlah_saham REAL DEFAULT 0,
            persentase REAL,
            tipe TEXT,
            updated_at TEXT,
            UNIQUE(kode, nama)
        )
    """),
    ("data_pasar_modal", "company_directors", "company_directors", """
        CREATE TABLE IF NOT EXISTS company_directors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kode TEXT NOT NULL,
            nama TEXT NOT NULL,
            jabatan TEXT,
            tipe TEXT DEFAULT 'DIREKTUR',
            created_at TEXT,
            UNIQUE(kode, nama, tipe)
        )
    """),
    ("data_pasar_modal", "broker_summary", "broker_summary", """
        CREATE TABLE IF NOT EXISTS broker_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tanggal TEXT NOT NULL,
            id_firm TEXT NOT NULL,
            firm_name TEXT,
            volume REAL DEFAULT 0,
            value REAL DEFAULT 0,
            frequency INTEGER DEFAULT 0,
            UNIQUE(tanggal, id_firm)
        )
    """),
    ("data_pasar_modal", "pattern_reliability", "pattern_reliability", """
        CREATE TABLE IF NOT EXISTS pattern_reliability (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kode TEXT,
            pattern TEXT NOT NULL,
            pattern_type TEXT DEFAULT 'bullish',
            total_occurrences INTEGER DEFAULT 0,
            success_count INTEGER DEFAULT 0,
            fail_count INTEGER DEFAULT 0,
            win_rate REAL DEFAULT 0,
            avg_return_5d REAL DEFAULT 0,
            avg_return_10d REAL DEFAULT 0,
            avg_return_20d REAL DEFAULT 0,
            max_return REAL DEFAULT 0,
            max_loss REAL DEFAULT 0,
            avg_confidence REAL DEFAULT 0,
            imperfect_winrate REAL DEFAULT 0,
            perfect_winrate REAL DEFAULT 0,
            last_detected TEXT,
            last_outcome TEXT DEFAULT 'pending',
            reliability_rating TEXT DEFAULT 'average',
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(kode, pattern)
        )
    """),
    ("data_pasar_modal", "pattern_candidates", "pattern_candidates", """
        CREATE TABLE IF NOT EXISTS pattern_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kode TEXT,
            pattern TEXT NOT NULL,
            pattern_type TEXT DEFAULT 'bullish',
            detected_at TEXT,
            detected_date TEXT,
            current_price REAL NOT NULL,
            latest_close REAL NOT NULL,
            trend_bias TEXT DEFAULT 'sideways',
            net_distribution_score REAL DEFAULT 50,
            preliminary_score REAL DEFAULT 50,
            preliminary_rating TEXT DEFAULT 'average',
            detected_by TEXT DEFAULT 'screener',
            status TEXT DEFAULT 'candidate',
            notes TEXT
        )
    """),
    ("data_pasar_modal", "advanced_features", "advanced_features", """
        CREATE TABLE IF NOT EXISTS advanced_features (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kode TEXT NOT NULL,
            order_flow TEXT,
            volume_profile TEXT,
            price_anomaly TEXT,
            volume_anomaly TEXT,
            market_regime TEXT,
            volatility_regime TEXT,
            advanced_score REAL,
            created_at TEXT
        )
    """),
    ("data_pasar_modal", "ai_scores_history", "ai_scores_history", """
        CREATE TABLE IF NOT EXISTS ai_scores_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tanggal TEXT NOT NULL,
            kode TEXT,
            skor INTEGER DEFAULT 50,
            sinyal TEXT DEFAULT 'HOLD',
            alasan TEXT,
            faktor_makro REAL DEFAULT 0,
            faktor_fundamental REAL DEFAULT 0,
            faktor_teknikal REAL DEFAULT 0,
            faktor_sentimen REAL DEFAULT 0,
            faktor_global REAL DEFAULT 0,
            created_at TEXT
        )
    """),
    # === idx_complete_data ===
    ("idx_complete_data", "sentiment_data", "idx_sentiment_data", """
        CREATE TABLE IF NOT EXISTS idx_sentiment_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            sentiment_score REAL,
            sentiment_label TEXT,
            news_count INTEGER DEFAULT 0,
            social_media_sentiment REAL,
            analyst_sentiment REAL,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(symbol, date)
        )
    """),
    ("idx_complete_data", "market_indices", "idx_market_indices", """
        CREATE TABLE IF NOT EXISTS idx_market_indices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            index_name TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(index_name, date)
        )
    """),
    ("idx_complete_data", "financial_statements", "idx_financial_statements", """
        CREATE TABLE IF NOT EXISTS idx_financial_statements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            period_type TEXT NOT NULL,
            period_date TEXT NOT NULL,
            total_revenue REAL,
            cost_of_revenue REAL,
            gross_profit REAL,
            operating_income REAL,
            net_income REAL,
            total_assets REAL,
            total_liabilities REAL,
            total_equity REAL,
            operating_cashflow REAL,
            free_cashflow REAL,
            updated_at TEXT,
            revenue REAL,
            total_debt REAL,
            pe_ratio REAL,
            pb_ratio REAL,
            roe REAL,
            debt_to_equity REAL,
            current_ratio REAL,
            profit_margin REAL,
            UNIQUE(symbol, period_type, period_date)
        )
    """),
    ("idx_complete_data", "social_media_sentiment", "idx_social_media_sentiment", """
        CREATE TABLE IF NOT EXISTS idx_social_media_sentiment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            platform TEXT NOT NULL,
            post_id TEXT,
            content TEXT,
            author TEXT,
            author_followers INTEGER,
            posted_at TEXT NOT NULL,
            sentiment_score REAL NOT NULL,
            sentiment_label TEXT NOT NULL,
            confidence REAL,
            engagement_score INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            retweets INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            hashtags TEXT,
            mentions TEXT,
            created_at TEXT
        )
    """),
    ("idx_complete_data", "stock_splits", "idx_stock_splits", """
        CREATE TABLE IF NOT EXISTS idx_stock_splits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            ratio REAL,
            updated_at TEXT,
            UNIQUE(symbol, date)
        )
    """),
    ("idx_complete_data", "quarterly_earnings", "idx_quarterly_earnings", """
        CREATE TABLE IF NOT EXISTS idx_quarterly_earnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            quarter_date TEXT NOT NULL,
            earnings REAL,
            revenue REAL,
            earnings_estimate REAL,
            revenue_estimate REAL,
            earnings_surprise REAL,
            revenue_surprise REAL,
            created_at TEXT,
            UNIQUE(symbol, quarter_date)
        )
    """),
]


def import_mysql_to_sqlite():
    print("=" * 70)
    print("Import MySQL → SQLite (tabel unik)")
    print("=" * 70)

    mysql_conn = pymysql.connect(**MYSQL_CONFIG)
    sqlite_conn = sqlite3.connect(str(DB_PATH))

    total_imported = 0
    total_tables = 0

    for mysql_db, mysql_table, sqlite_table, create_sql in IMPORT_LIST:
        print(f"\n  [{mysql_db}.{mysql_table}] → [{sqlite_table}]")

        # Create SQLite table
        sqlite_conn.execute(create_sql)
        sqlite_conn.commit()

        # Check existing
        cur = sqlite_conn.execute(f"SELECT COUNT(*) FROM {sqlite_table}")
        existing = cur.fetchone()[0]
        if existing > 0:
            print(f"    Already has {existing:,} rows, skipping")
            continue

        # Read from MySQL in chunks
        try:
            # Get column names
            cur_mysql = mysql_conn.cursor()
            cur_mysql.execute(f"SELECT * FROM `{mysql_db}`.`{mysql_table}` LIMIT 0")
            columns = [desc[0] for desc in cur_mysql.description]

            # Read all data
            df = pd.read_sql(
                f"SELECT * FROM `{mysql_db}`.`{mysql_table}`",
                mysql_conn,
            )

            if df.empty:
                print(f"    Empty table, skipping")
                continue

            # Drop 'id' column (auto-increment)
            if "id" in df.columns:
                df = df.drop(columns=["id"])

            # Convert datetime columns to string
            for c in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[c]):
                    df[c] = df[c].astype(str)
                elif df[c].dtype == object and len(df) > 0:
                    if hasattr(df[c].iloc[0], "strftime"):
                        df[c] = df[c].astype(str)

            # Get SQLite columns
            cur_sqlite = sqlite_conn.execute(f"PRAGMA table_info({sqlite_table})")
            db_cols = [r[1] for r in cur_sqlite.fetchall()]
            df = df[[c for c in df.columns if c in db_cols]]

            if df.empty:
                print(f"    No matching columns, skipping")
                continue

            # Insert
            placeholders = ",".join(["?" for _ in df.columns])
            col_names = ",".join(df.columns)
            rows = [tuple(x) for x in df.itertuples(index=False, name=None)]

            sqlite_conn.executemany(
                f"INSERT OR IGNORE INTO {sqlite_table} ({col_names}) VALUES ({placeholders})",
                rows,
            )
            sqlite_conn.commit()

            inserted = len(rows)
            total_imported += inserted
            total_tables += 1
            print(f"    [OK] {inserted:>10,} rows imported")

        except Exception as e:
            print(f"    [FAIL] {e}")
            sqlite_conn.rollback()

    mysql_conn.close()
    sqlite_conn.close()

    print(f"\n{'=' * 70}")
    print(f"Total: {total_tables} tables, {total_imported:,} rows imported")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    import_mysql_to_sqlite()
