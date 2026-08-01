#!/usr/bin/env python3
"""
Import data lengkap dari MySQL (data_pasar_modal + idx_complete_data) dan Parquet
ke SQLite trading_system.db.

Sumber data:
  1. MySQL data_pasar_modal (67 tabel, ~2.2M rows) — sumber utama
  2. MySQL idx_complete_data (48 tabel, ~1.3M rows) — sumber sekunder
  3. Parquet /media/petrick/Expansion/trading_data/raw/ (174 file, ~1.6M rows) — data arsip

Strategi: INSERT OR REPLACE untuk deduplikasi. Data terbaru menang.
"""

import os
import sys
import sqlite3
import time
import warnings
from datetime import datetime
from decimal import Decimal
from pathlib import Path


def to_float(v):
    """Convert Decimal/None/str to float or None."""
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def to_str(v):
    """Convert any value to string or None."""
    if v is None:
        return None
    return str(v)

warnings.filterwarnings("ignore")

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# MySQL config
MYSQL_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "root",
    "unix_socket": "/opt/lampp/var/mysql/mysql.sock",
}

# Paths
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "trading_system.db"
PARQUET_DIR = "/media/petrick/Expansion/trading_data/raw"

# Ticker suffix mapping: MySQL uses bare ticker (BBCA), SQLite uses .JK
TICKER_SUFFIX = ".JK"


def get_mysql_conn():
    import pymysql
    return pymysql.connect(
        host=MYSQL_CONFIG["host"],
        user=MYSQL_CONFIG["user"],
        password=MYSQL_CONFIG["password"],
        unix_socket=MYSQL_CONFIG["unix_socket"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.SSCursor,  # Server-side cursor for large queries
    )


def to_jk(ticker: str) -> str:
    """Add .JK suffix if not present and ticker looks like IDX stock."""
    if not ticker:
        return ticker
    ticker = ticker.strip()
    if "." in ticker or ticker.startswith("^") or "=" in ticker:
        return ticker
    return f"{ticker}{TICKER_SUFFIX}"


def norm_date(d) -> str:
    """Normalize date to YYYY-MM-DD string."""
    if d is None:
        return None
    if isinstance(d, str):
        return d[:10]
    if hasattr(d, "strftime"):
        return d.strftime("%Y-%m-%d")
    return str(d)[:10]


def norm_dt(d) -> str:
    """Normalize datetime to ISO string."""
    if d is None:
        return None
    if isinstance(d, str):
        return d
    if hasattr(d, "strftime"):
        return d.strftime("%Y-%m-%d %H:%M:%S")
    return str(d)


def batch_insert(sqlite_cur, sql, rows, batch_size=5000):
    """Insert rows in batches."""
    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        sqlite_cur.executemany(sql, batch)
        total += len(batch)
    return total


def progress(name, count, total=None):
    ts = datetime.now().strftime("%H:%M:%S")
    if total:
        pct = count * 100 // total if total else 0
        print(f"  [{ts}] {name}: {count:,}/{total:,} ({pct}%)")
    else:
        print(f"  [{ts}] {name}: {count:,} rows")


# ============================================================
# 1. IMPORT STOCK_HISTORY → ohlcv  (1.93M rows — terbesar)
# ============================================================
def import_stock_history(mysql_conn, sqlite_cur):
    print("\n[1] Import stock_history → ohlcv")
    cur = mysql_conn.cursor()
    cur.execute("SELECT COUNT(*) FROM data_pasar_modal.stock_history")
    total = cur.fetchone()[0]
    print(f"  Total rows: {total:,}")

    cur.execute("""
        SELECT kode, tanggal, open, high, low, close, adj_close, volume
        FROM data_pasar_modal.stock_history
        ORDER BY kode, tanggal
    """)

    sql = """
        INSERT OR REPLACE INTO ohlcv
        (ticker, asset_class, exchange, timestamp, timeframe, open, high, low, close, volume, adjusted_close, source, ingested_at, data_quality_score)
        VALUES (?, 'equity', 'IDX', ?, '1d', ?, ?, ?, ?, ?, ?, 'mysql_import', ?, NULL)
    """

    batch = []
    count = 0
    for row in cur:
        kode, tanggal, o, h, l, c, ac, v = row
        ticker = to_jk(kode)
        ts = norm_date(tanggal)
        batch.append((ticker, ts, to_float(o), to_float(h), to_float(l), to_float(c), to_float(v), to_float(ac) if ac else to_float(c), datetime.now().isoformat()))
        if len(batch) >= 5000:
            sqlite_cur.executemany(sql, batch)
            batch.clear()
            count += 5000
            if count % 50000 == 0:
                progress("stock_history", count, total)

    if batch:
        sqlite_cur.executemany(sql, batch)
        count += len(batch)

    cur.close()
    progress("stock_history DONE", count, total)
    return count


# ============================================================
# 2. IMPORT SAHAM → instrument_master + sector_master
# ============================================================
def import_saham(mysql_conn, sqlite_cur):
    print("\n[2] Import saham → instrument_master + sector_master")
    cur = mysql_conn.cursor()
    cur.execute("SELECT kode, nama, sektor, harga, per, pbv, roe, der, market_cap, ipo_date, status, delisted_date FROM data_pasar_modal.saham")
    rows = cur.fetchall()

    # Sector master
    sectors = {}
    for r in rows:
        sektor = r[2]
        if sektor and sektor not in sectors:
            sectors[sektor] = sektor

    for s_name in sectors:
        sqlite_cur.execute("INSERT OR REPLACE INTO sector_master VALUES (?, ?, NULL, NULL, ?)", (s_name, s_name, datetime.now().isoformat()))

    # Instrument master
    sql = """
        INSERT OR REPLACE INTO instrument_master
        (ticker, name, sector, subsector, exchange, listing_date, delisting_date, is_active, board, market_cap, free_float, updated_at)
        VALUES (?, ?, ?, NULL, 'IDX', ?, ?, ?, NULL, ?, NULL, ?)
    """
    count = 0
    for r in rows:
        kode, nama, sektor, harga, per, pbv, roe, der, market_cap, ipo_date, status, delisted_date = r
        ticker = to_jk(kode)
        is_active = 1 if status and status.upper() == "ACTIVE" else 0
        sqlite_cur.execute(sql, (
            ticker, nama, sektor,
            norm_date(ipo_date), norm_date(delisted_date),
            is_active, to_float(market_cap), datetime.now().isoformat()
        ))
        count += 1

    cur.close()
    progress("saham → instrument_master", count)
    return count


# ============================================================
# 3. IMPORT SAHAM_FUNDAMENTAL → fundamental_data
# ============================================================
def import_fundamental(mysql_conn, sqlite_cur):
    print("\n[3] Import saham_fundamental → fundamental_data")
    cur = mysql_conn.cursor()
    cur.execute("SELECT kode, periode, eps, revenue, net_profit, total_equity, book_value_per_share, npm, revenue_growth, profit_growth FROM data_pasar_modal.saham_fundamental")
    rows = cur.fetchall()

    sql = """
        INSERT OR REPLACE INTO fundamental_data
        (ticker, date, pe_ratio, pb_ratio, roe, debt_to_equity, dividend_yield,
         earnings_per_share, book_value_per_share, net_profit, revenue,
         total_assets, total_liabilities, cash_flow, fiscal_year, quarter, source)
        VALUES (?, ?, NULL, NULL, NULL, NULL, NULL, ?, ?, ?, ?, NULL, NULL, NULL, ?, NULL, 'mysql_import')
    """
    count = 0
    batch = []
    for r in rows:
        kode, periode, eps, revenue, net_profit, total_equity, bvps, npm, rev_g, profit_g = r
        ticker = to_jk(kode)
        date_str = str(periode) if periode else None
        # Try to parse fiscal year from periode
        fy = None
        if periode:
            try:
                fy = int(str(periode)[:4])
            except (ValueError, TypeError):
                pass
        batch.append((ticker, date_str, to_float(eps), to_float(bvps), to_float(net_profit), to_float(revenue), fy))
        if len(batch) >= 1000:
            sqlite_cur.executemany(sql, batch)
            batch.clear()
            count += 1000

    if batch:
        sqlite_cur.executemany(sql, batch)
        count += len(batch)

    cur.close()
    progress("saham_fundamental → fundamental_data", count)
    return count


# ============================================================
# 4. IMPORT SAHAM_SNAPSHOT → fundamental_data (PER, PBV, ROE, DER, market_cap)
# ============================================================
def import_snapshots(mysql_conn, sqlite_cur):
    print("\n[4] Import saham_snapshot → fundamental_data (daily PER/PBV/ROE/DER)")
    cur = mysql_conn.cursor()
    cur.execute("SELECT COUNT(*) FROM data_pasar_modal.saham_snapshot")
    total = cur.fetchone()[0]
    print(f"  Total rows: {total:,}")

    cur.execute("SELECT kode, tanggal, harga, per, pbv, roe, der, market_cap, volume FROM data_pasar_modal.saham_snapshot ORDER BY kode, tanggal")

    sql = """
        INSERT OR REPLACE INTO fundamental_data
        (ticker, date, pe_ratio, pb_ratio, roe, debt_to_equity, dividend_yield,
         earnings_per_share, book_value_per_share, net_profit, revenue,
         total_assets, total_liabilities, cash_flow, fiscal_year, quarter, source)
        VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 'snapshot_import')
    """
    batch = []
    count = 0
    for row in cur:
        kode, tanggal, harga, per, pbv, roe, der, market_cap, volume = row
        ticker = to_jk(kode)
        date_str = norm_date(tanggal)
        batch.append((ticker, date_str, to_float(per), to_float(pbv), to_float(roe), to_float(der)))
        if len(batch) >= 5000:
            sqlite_cur.executemany(sql, batch)
            batch.clear()
            count += 5000
            if count % 50000 == 0:
                progress("saham_snapshot", count, total)

    if batch:
        sqlite_cur.executemany(sql, batch)
        count += len(batch)

    cur.close()
    progress("saham_snapshot DONE", count, total)
    return count


# ============================================================
# 5. IMPORT BROKER_FLOW → broker_flow + foreign_flow
# ============================================================
def import_broker_flow(mysql_conn, sqlite_cur):
    print("\n[5] Import broker_flow → foreign_flow")
    cur = mysql_conn.cursor()
    cur.execute("SELECT COUNT(*) FROM data_pasar_modal.broker_flow")
    total = cur.fetchone()[0]
    print(f"  Total rows: {total:,}")

    cur.execute("SELECT kode, tanggal, foreign_buy, foreign_sell, foreign_net, domestic_buy, domestic_sell, domestic_net, total_volume, total_value FROM data_pasar_modal.broker_flow ORDER BY kode, tanggal")

    sql = """
        INSERT OR REPLACE INTO foreign_flow
        (ticker, date, foreign_buy, foreign_sell, foreign_net, domestic_buy, domestic_sell, domestic_net, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'mysql_import')
    """
    batch = []
    count = 0
    for row in cur:
        kode, tanggal, fb, fs, fn, db, ds, dn, tv, tval = row
        ticker = to_jk(kode)
        date_str = norm_date(tanggal)
        batch.append((ticker, date_str, to_float(fb), to_float(fs), to_float(fn), to_float(db), to_float(ds), to_float(dn)))
        if len(batch) >= 5000:
            sqlite_cur.executemany(sql, batch)
            batch.clear()
            count += 5000
            if count % 20000 == 0:
                progress("broker_flow", count, total)

    if batch:
        sqlite_cur.executemany(sql, batch)
        count += len(batch)

    cur.close()
    progress("broker_flow DONE", count, total)
    return count


# ============================================================
# 6. IMPORT DIVIDEND → dividends
# ============================================================
def import_dividends(mysql_conn, sqlite_cur):
    print("\n[6] Import dividend → dividends")
    cur = mysql_conn.cursor()
    cur.execute("SELECT kode, ex_date, record_date, payment_date, amount_per_share, tipe, dividend_yield FROM data_pasar_modal.dividend")
    rows = cur.fetchall()

    sql = """
        INSERT OR REPLACE INTO dividends
        (ticker, ex_date, record_date, payment_date, amount, currency, frequency, source)
        VALUES (?, ?, ?, ?, ?, 'IDR', ?, 'mysql_import')
    """
    batch = []
    for r in rows:
        kode, ex_date, record_date, payment_date, amount, tipe, dy = r
        ticker = to_jk(kode)
        batch.append((ticker, norm_date(ex_date), norm_date(record_date), norm_date(payment_date), to_float(amount), tipe))

    if batch:
        sqlite_cur.executemany(sql, batch)
    cur.close()
    progress("dividend → dividends", len(batch))
    return len(batch)


# ============================================================
# 7. IMPORT CORPORATE_ACTIONS → corporate_actions
# ============================================================
def import_corporate_actions(mysql_conn, sqlite_cur):
    print("\n[7] Import corporate_actions → corporate_actions")
    cur = mysql_conn.cursor()
    cur.execute("SELECT GROUP_CONCAT(COLUMN_NAME) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='data_pasar_modal' AND TABLE_NAME='corporate_actions' ORDER BY ORDINAL_POSITION")
    cols = cur.fetchone()[0]
    print(f"  Columns: {cols}")

    cur.execute("SELECT * FROM data_pasar_modal.corporate_actions")
    rows = cur.fetchall()
    col_list = cols.split(",")

    sql = """
        INSERT OR REPLACE INTO corporate_actions
        (ticker, action_type, announce_date, ex_date, record_date, payment_date, value, unit, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'mysql_import')
    """
    batch = []
    for r in rows:
        row = dict(zip(col_list, r))
        kode = row.get("kode", "")
        ticker = to_jk(kode)
        action_type = row.get("jenis", row.get("action_type", row.get("tipe", "")))
        ex_date = norm_date(row.get("ex_date", row.get("tanggal", row.get("date"))))
        announce_date = norm_date(row.get("announce_date", row.get("created_at")))
        record_date = norm_date(row.get("record_date"))
        payment_date = norm_date(row.get("payment_date"))
        value = row.get("rasio", row.get("amount", row.get("nilai", row.get("value"))))
        unit = row.get("unit", row.get("satuan", "ratio"))
        batch.append((ticker, action_type, announce_date, ex_date, record_date, payment_date, to_float(value), unit))

    if batch:
        sqlite_cur.executemany(sql, batch)
    cur.close()
    progress("corporate_actions", len(batch))
    return len(batch)


# ============================================================
# 8. IMPORT INDIKATOR_TEKNIKAL → technical_indicators
# ============================================================
def import_technical_indicators(mysql_conn, sqlite_cur):
    print("\n[8] Import indikator_teknikal → technical_indicators")
    cur = mysql_conn.cursor()
    cur.execute("SELECT kode, tanggal, rsi, macd, ma20, ma50, ma200, stochastic, support, resistance, `signal` FROM data_pasar_modal.indikator_teknikal")
    rows = cur.fetchall()

    sql = """
        INSERT OR REPLACE INTO technical_indicators
        (ticker, date, indicator, value, timeframe, source)
        VALUES (?, ?, ?, ?, '1d', 'mysql_import')
    """
    # Column indices in the SELECT: 0=kode, 1=tanggal, 2=rsi, 3=macd, 4=ma20, 5=ma50, 6=ma200, 7=stochastic, 8=support, 9=resistance, 10=signal
    indicators_map = {
        2: "rsi", 3: "macd", 4: "ma20", 5: "ma50", 6: "ma200",
        7: "stochastic", 8: "support", 9: "resistance",
    }
    batch = []
    for r in rows:
        kode = r[0]
        ticker = to_jk(kode)
        date_str = norm_date(r[1])
        for idx, ind_name in indicators_map.items():
            val = r[idx] if idx < len(r) else None
            fval = to_float(val)
            if fval is not None:
                batch.append((ticker, date_str, ind_name, fval))

    if batch:
        # Insert in chunks
        for i in range(0, len(batch), 5000):
            sqlite_cur.executemany(sql, batch[i:i+5000])
    cur.close()
    progress("indikator_teknikal → technical_indicators", len(batch))
    return len(batch)


# ============================================================
# 9. IMPORT BERITA_SENTIMEN → news
# ============================================================
def import_sentiment_news(mysql_conn, sqlite_cur):
    print("\n[9] Import berita_sentimen → news")
    cur = mysql_conn.cursor()
    cur.execute("SELECT id, tanggal, judul, sentimen, sumber, kode FROM data_pasar_modal.berita_sentimen")
    rows = cur.fetchall()

    sql = """
        INSERT OR REPLACE INTO news
        (news_id, headline, body, published_at, source, entities, topic, sentiment, impact)
        VALUES (?, ?, NULL, ?, ?, ?, NULL, ?, NULL)
    """
    batch = []
    for r in rows:
        nid, tanggal, judul, sentimen, sumber, kode = r
        news_id = f"mysql_{nid}"
        date_str = norm_date(tanggal)
        entities = to_jk(kode) if kode else None
        batch.append((news_id, judul, date_str, sumber, entities, to_float(sentimen)))

    if batch:
        sqlite_cur.executemany(sql, batch)
    cur.close()
    progress("berita_sentimen → news", len(batch))
    return len(batch)


# ============================================================
# 10. IMPORT FEAR_GREAD_INDEX → fear_greed
# ============================================================
def import_fear_greed(mysql_conn, sqlite_cur):
    print("\n[10] Import fear_greed_index → fear_greed")
    cur = mysql_conn.cursor()
    cur.execute("SELECT tanggal, nilai, label FROM data_pasar_modal.fear_greed_index")
    rows = cur.fetchall()

    sql = "INSERT OR REPLACE INTO fear_greed VALUES (?, ?, ?, 'mysql_import', ?)"
    batch = []
    for r in rows:
        tanggal, nilai, label = r
        batch.append((norm_date(tanggal), to_float(nilai), label, datetime.now().isoformat()))

    if batch:
        sqlite_cur.executemany(sql, batch)
    cur.close()
    progress("fear_greed_index", len(batch))
    return len(batch)


# ============================================================
# 11. IMPORT MAKROEKONOMI → macro_data
# ============================================================
def import_macro(mysql_conn, sqlite_cur):
    print("\n[11] Import makroekonomi → macro_data")
    cur = mysql_conn.cursor()
    cur.execute("SELECT periode, inflasi, suku_bunga, kurs_usd, gdp_growth, pengangguran, neraca_perdagangan FROM data_pasar_modal.makroekonomi")
    rows = cur.fetchall()

    sql = "INSERT OR REPLACE INTO macro_data VALUES (?, ?, ?, ?, 'mysql_import', 'monthly')"
    indicators = {
        1: ("inflation", "%"),
        2: ("interest_rate", "%"),
        3: ("usd_idr", "IDR"),
        4: ("gdp_growth", "%"),
        5: ("unemployment", "%"),
        6: ("trade_balance", "USD"),
    }
    batch = []
    for r in rows:
        periode = r[0]
        date_str = str(periode) if periode else None
        for idx, (name, unit) in indicators.items():
            val = r[idx] if idx < len(r) else None
            fval = to_float(val)
            if fval is not None:
                batch.append((name, date_str, fval, unit))

    if batch:
        sqlite_cur.executemany(sql, batch)
    cur.close()
    progress("makroekonomi → macro_data", len(batch))
    return len(batch)


# ============================================================
# 12. IMPORT KOMODITAS → macro_data
# ============================================================
def import_commodity(mysql_conn, sqlite_cur):
    print("\n[12] Import komoditas → macro_data")
    cur = mysql_conn.cursor()
    cur.execute("SELECT nama, tanggal, nilai, perubahan, satuan FROM data_pasar_modal.komoditas")
    rows = cur.fetchall()

    sql = "INSERT OR REPLACE INTO macro_data VALUES (?, ?, ?, ?, 'mysql_import', 'daily')"
    batch = []
    for r in rows:
        nama, tanggal, nilai, perubahan, satuan = r
        name = f"commodity_{nama}" if nama else None
        if name and nilai is not None:
            batch.append((name, norm_date(tanggal), to_float(nilai), satuan or ""))

    if batch:
        sqlite_cur.executemany(sql, batch)
    cur.close()
    progress("komoditas → macro_data", len(batch))
    return len(batch)


# ============================================================
# 13. IMPORT IHSG_HISTORY → ohlcv (as index)
# ============================================================
def import_ihsg(mysql_conn, sqlite_cur):
    print("\n[13] Import ihsg_history → ohlcv (as ^JKSE index)")
    cur = mysql_conn.cursor()
    cur.execute("SELECT tanggal, harga, perubahan, volume FROM data_pasar_modal.ihsg_history")
    rows = cur.fetchall()

    sql = """
        INSERT OR REPLACE INTO ohlcv
        (ticker, asset_class, exchange, timestamp, timeframe, open, high, low, close, volume, adjusted_close, source, ingested_at, data_quality_score)
        VALUES ('^JKSE', 'index', 'IDX', ?, '1d', ?, ?, ?, ?, ?, ?, 'mysql_import', ?, NULL)
    """
    batch = []
    for r in rows:
        tanggal, harga, perubahan, volume = r
        date_str = norm_date(tanggal)
        # We only have close; use close for all OHLC
        batch.append((date_str, to_float(harga), to_float(harga), to_float(harga), to_float(harga), to_float(volume), to_float(harga), datetime.now().isoformat()))

    if batch:
        sqlite_cur.executemany(sql, batch)
    cur.close()
    progress("ihsg_history → ohlcv (^JKSE)", len(batch))
    return len(batch)


# ============================================================
# 14. IMPORT BURSA_GLOBAL → ohlcv (global indices)
# ============================================================
def import_global_indices(mysql_conn, sqlite_cur):
    print("\n[14] Import bursa_global → ohlcv (global indices)")
    cur = mysql_conn.cursor()
    cur.execute("SELECT GROUP_CONCAT(COLUMN_NAME) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='data_pasar_modal' AND TABLE_NAME='bursa_global' ORDER BY ORDINAL_POSITION")
    cols = cur.fetchone()[0]
    print(f"  Columns: {cols}")
    col_list = cols.split(",")

    cur.execute("SELECT * FROM data_pasar_modal.bursa_global")
    rows = cur.fetchall()

    sql = """
        INSERT OR REPLACE INTO ohlcv
        (ticker, asset_class, exchange, timestamp, timeframe, open, high, low, close, volume, adjusted_close, source, ingested_at, data_quality_score)
        VALUES (?, 'index', ?, ?, '1d', ?, ?, ?, ?, ?, ?, 'mysql_import', ?, NULL)
    """
    batch = []
    for r in rows:
        row = dict(zip(col_list, r))
        nama = row.get("nama", row.get("kode", ""))
        ticker = row.get("kode", row.get("ticker", nama))
        tanggal = row.get("tanggal", row.get("date"))
        close = row.get("harga", row.get("close", row.get("nilai")))
        if ticker and tanggal and close is not None:
            exchange = row.get("exchange", "GLOBAL")
            batch.append((ticker, exchange, norm_date(tanggal), to_float(close), to_float(close), to_float(close), to_float(close), 0, to_float(close), datetime.now().isoformat()))

    if batch:
        sqlite_cur.executemany(sql, batch)
    cur.close()
    progress("bursa_global → ohlcv", len(batch))
    return len(batch)


# ============================================================
# 15. IMPORT MULTI_ASSET → ohlcv (commodities, forex)
# ============================================================
def import_multi_asset(mysql_conn, sqlite_cur):
    print("\n[15] Import multi_asset → ohlcv")
    cur = mysql_conn.cursor()
    cur.execute("SELECT kode, tanggal, harga, change_pct, jenis, nama FROM data_pasar_modal.multi_asset")
    rows = cur.fetchall()

    sql = """
        INSERT OR REPLACE INTO ohlcv
        (ticker, asset_class, exchange, timestamp, timeframe, open, high, low, close, volume, adjusted_close, source, ingested_at, data_quality_score)
        VALUES (?, ?, 'GLOBAL', ?, '1d', ?, ?, ?, ?, 0, ?, 'mysql_import', ?, NULL)
    """
    batch = []
    for r in rows:
        kode, tanggal, harga, change_pct, jenis, nama = r
        if kode and tanggal and harga is not None:
            asset_class = "commodity" if jenis and "komoditas" in str(jenis).lower() else "forex" if jenis and "forex" in str(jenis).lower() else "index"
            batch.append((kode, asset_class, norm_date(tanggal), to_float(harga), to_float(harga), to_float(harga), to_float(harga), to_float(harga), datetime.now().isoformat()))

    if batch:
        sqlite_cur.executemany(sql, batch)
    cur.close()
    progress("multi_asset → ohlcv", len(batch))
    return len(batch)


# ============================================================
# 16. IMPORT STOCK_PERSONALITY → stock_personality
# ============================================================
def import_stock_personality(mysql_conn, sqlite_cur):
    print("\n[16] Import stock_personality → stock_personality")
    cur = mysql_conn.cursor()
    cur.execute("""
        SELECT kode, profile_date, avg_daily_volatility, volatility_regime, trend_bias, trend_strength,
               avg_uptrend_streak, avg_downtrend_streak, beta_vs_ihsg, correlation_ihsg,
               volume_consistency, liquidity_score, net_distribution_score, personality_label
        FROM data_pasar_modal.stock_personality
    """)
    rows = cur.fetchall()

    sql = """
        INSERT OR REPLACE INTO stock_personality
        (ticker, personality_type, volatility_profile, liquidity_profile, beta, correlation_to_ihsg, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    batch = []
    for r in rows:
        kode, profile_date, vol, vol_regime, trend_bias, trend_str, up_streak, dn_streak, beta, corr, vol_cons, liq_score, net_dist, label = r
        ticker = to_jk(kode)
        vol_profile = f"{vol_regime or 'unknown'} (vol={vol})"
        liq_profile = f"score={liq_score}" if liq_score else "unknown"
        batch.append((ticker, label or trend_bias or "unknown", vol_profile, liq_profile, to_float(beta), to_float(corr), norm_date(profile_date)))

    if batch:
        sqlite_cur.executemany(sql, batch)
    cur.close()
    progress("stock_personality", len(batch))
    return len(batch)


# ============================================================
# 17. IMPORT VALUATION_CACHE → valuation_cache
# ============================================================
def import_valuation(mysql_conn, sqlite_cur):
    print("\n[17] Import valuation_cache → valuation_cache")
    cur = mysql_conn.cursor()
    cur.execute("SELECT kode, computed_at, method, intrinsic_value, margin_of_safety, assumptions FROM data_pasar_modal.valuation_cache")
    rows = cur.fetchall()

    sql = """
        INSERT OR REPLACE INTO valuation_cache
        (ticker, date, method, intrinsic_value, market_price, upside_pct, assumptions, source)
        VALUES (?, ?, ?, ?, NULL, ?, ?, 'mysql_import')
    """
    batch = []
    for r in rows:
        kode, computed_at, method, iv, mos, assumptions = r
        ticker = to_jk(kode)
        batch.append((ticker, norm_date(computed_at), method, to_float(iv), to_float(mos), str(assumptions) if assumptions else None))

    if batch:
        sqlite_cur.executemany(sql, batch)
    cur.close()
    progress("valuation_cache", len(batch))
    return len(batch)


# ============================================================
# 18. IMPORT CHART_PATTERNS → pattern_analysis
# ============================================================
def import_chart_patterns(mysql_conn, sqlite_cur):
    print("\n[18] Import chart_patterns → pattern_analysis")
    cur = mysql_conn.cursor()
    cur.execute("SELECT GROUP_CONCAT(COLUMN_NAME) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='data_pasar_modal' AND TABLE_NAME='chart_patterns' ORDER BY ORDINAL_POSITION")
    cols = cur.fetchone()[0]
    col_list = cols.split(",")
    print(f"  Columns: {cols}")

    cur.execute("SELECT * FROM data_pasar_modal.chart_patterns LIMIT 50000")
    rows = cur.fetchall()

    sql = """
        INSERT INTO pattern_analysis
        (ticker, date, pattern_type, confidence, direction, details, source, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'mysql_import', ?)
    """
    batch = []
    for r in rows:
        row = dict(zip(col_list, r))
        kode = row.get("kode", "")
        ticker = to_jk(kode)
        pattern = row.get("pattern", row.get("pattern_type", ""))
        date = norm_date(row.get("tanggal", row.get("detected_date", row.get("date"))))
        confidence = to_float(row.get("confidence", row.get("reliability", 0)))
        direction = row.get("direction", row.get("trend_bias", ""))
        details = str({k: v for k, v in row.items() if v is not None and k not in ("id", "kode")})
        batch.append((ticker, date, pattern, confidence, direction, details, datetime.now().isoformat()))

    if batch:
        sqlite_cur.executemany(sql, batch)
    cur.close()
    progress("chart_patterns → pattern_analysis", len(batch))
    return len(batch)


# ============================================================
# 19. IMPORT KEBIJAKAN_REGULASI → policy_events
# ============================================================
def import_policy_events(mysql_conn, sqlite_cur):
    print("\n[19] Import kebijakan_regulasi → policy_events")
    cur = mysql_conn.cursor()
    cur.execute("SELECT tanggal, judul, kategori, dampak, instansi, deskripsi FROM data_pasar_modal.kebijakan_regulasi")
    rows = cur.fetchall()

    sql = """
        INSERT INTO policy_events
        (date, event_type, description, impact, source, created_at)
        VALUES (?, ?, ?, ?, 'mysql_import', ?)
    """
    batch = []
    for r in rows:
        tanggal, judul, kategori, dampak, instansi, deskripsi = r
        batch.append((norm_date(tanggal), kategori or "regulation", f"{judul} - {deskripsi or ''}", dampak, datetime.now().isoformat()))

    if batch:
        sqlite_cur.executemany(sql, batch)
    cur.close()
    progress("kebijakan_regulasi → policy_events", len(batch))
    return len(batch)


# ============================================================
# 20. IMPORT EVENT_EKSTERNAL → external_events
# ============================================================
def import_external_events(mysql_conn, sqlite_cur):
    print("\n[20] Import event_eksternal → external_events")
    cur = mysql_conn.cursor()
    cur.execute("SELECT tanggal, judul, kategori, dampak_market, lokasi, deskripsi FROM data_pasar_modal.event_eksternal")
    rows = cur.fetchall()

    sql = """
        INSERT INTO external_events
        (date, event_type, description, region, impact_level, source, created_at)
        VALUES (?, ?, ?, ?, ?, 'mysql_import', ?)
    """
    batch = []
    for r in rows:
        tanggal, judul, kategori, dampak, lokasi, deskripsi = r
        batch.append((norm_date(tanggal), kategori or "external", f"{judul} - {deskripsi or ''}", lokasi or "ID", dampak, datetime.now().isoformat()))

    if batch:
        sqlite_cur.executemany(sql, batch)
    cur.close()
    progress("event_eksternal → external_events", len(batch))
    return len(batch)


# ============================================================
# 21. IMPORT ESG_SCORES → esg_scores
# ============================================================
def import_esg(mysql_conn, sqlite_cur):
    print("\n[21] Import esg_scores → esg_scores")
    cur = mysql_conn.cursor()
    cur.execute("SELECT kode, year, score, rating, rating_agency FROM data_pasar_modal.esg_scores")
    rows = cur.fetchall()

    sql = """
        INSERT OR REPLACE INTO esg_scores
        (ticker, date, e_score, s_score, g_score, esg_score, source)
        VALUES (?, ?, NULL, NULL, NULL, ?, 'mysql_import')
    """
    batch = []
    for r in rows:
        kode, year, score, rating, agency = r
        ticker = to_jk(kode)
        date_str = f"{year}-12-31" if year else None
        batch.append((ticker, date_str, to_float(score)))

    if batch:
        sqlite_cur.executemany(sql, batch)
    cur.close()
    progress("esg_scores", len(batch))
    return len(batch)


# ============================================================
# 22. IMPORT CORPORATE_GOVERNANCE → corporate_governance
# ============================================================
def import_corp_governance(mysql_conn, sqlite_cur):
    print("\n[22] Import corporate_governance → corporate_governance")
    cur = mysql_conn.cursor()
    cur.execute("SELECT GROUP_CONCAT(COLUMN_NAME) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='data_pasar_modal' AND TABLE_NAME='corporate_governance' ORDER BY ORDINAL_POSITION")
    cols = cur.fetchone()[0]
    col_list = cols.split(",")

    cur.execute("SELECT * FROM data_pasar_modal.corporate_governance")
    rows = cur.fetchall()

    sql = """
        INSERT OR REPLACE INTO corporate_governance
        (ticker, date, board_size, independent_directors, audit_committee_quality, ownership_concentration, source)
        VALUES (?, ?, ?, ?, ?, ?, 'mysql_import')
    """
    batch = []
    for r in rows:
        row = dict(zip(col_list, r))
        kode = row.get("kode", "")
        ticker = to_jk(kode)
        year = row.get("year", "")
        date_str = f"{year}-12-31" if year else norm_date(row.get("created_at"))
        board_size = row.get("board_commissioners") or row.get("board_size")
        indep = row.get("independent_commissioners") or row.get("independent_directors")
        audit = row.get("audit_committee") or row.get("audit_committee_quality")
        ownership = row.get("ownership_concentration")
        batch.append((ticker, date_str, board_size, indep, audit, ownership))

    if batch:
        sqlite_cur.executemany(sql, batch)
    cur.close()
    progress("corporate_governance", len(batch))
    return len(batch)


# ============================================================
# 23. IMPORT IDX_COMPLETE_DATA — daily_prices (supplement)
# ============================================================
def import_idx_daily_prices(mysql_conn, sqlite_cur):
    print("\n[23] Import idx_complete_data.daily_prices → ohlcv (supplement)")
    cur = mysql_conn.cursor()
    cur.execute("SELECT COUNT(*) FROM idx_complete_data.daily_prices")
    total = cur.fetchone()[0]
    print(f"  Total rows: {total:,}")

    cur.execute("SELECT symbol, date, open, high, low, close, volume, adj_close FROM idx_complete_data.daily_prices ORDER BY symbol, date")

    sql = """
        INSERT OR REPLACE INTO ohlcv
        (ticker, asset_class, exchange, timestamp, timeframe, open, high, low, close, volume, adjusted_close, source, ingested_at, data_quality_score)
        VALUES (?, 'equity', 'IDX', ?, '1d', ?, ?, ?, ?, ?, ?, 'idx_complete', ?, NULL)
    """
    batch = []
    count = 0
    for row in cur:
        symbol, date, o, h, l, c, v, ac = row
        ticker = to_jk(symbol)
        ts = norm_date(date)
        batch.append((ticker, ts, to_float(o), to_float(h), to_float(l), to_float(c), to_float(v), to_float(ac) if ac else to_float(c), datetime.now().isoformat()))
        if len(batch) >= 5000:
            sqlite_cur.executemany(sql, batch)
            batch.clear()
            count += 5000
            if count % 100000 == 0:
                progress("idx daily_prices", count, total)

    if batch:
        sqlite_cur.executemany(sql, batch)
        count += len(batch)

    cur.close()
    progress("idx daily_prices DONE", count, total)
    return count


# ============================================================
# 24. IMPORT IDX_COMPLETE_DATA — sentiment_data → news
# ============================================================
def import_idx_sentiment(mysql_conn, sqlite_cur):
    print("\n[24] Import idx_complete_data.sentiment_data → news")
    cur = mysql_conn.cursor()
    cur.execute("SELECT GROUP_CONCAT(COLUMN_NAME) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='idx_complete_data' AND TABLE_NAME='sentiment_data' ORDER BY ORDINAL_POSITION")
    cols = cur.fetchone()[0]
    col_list = cols.split(",")
    print(f"  Columns: {cols}")

    cur.execute("SELECT * FROM idx_complete_data.sentiment_data LIMIT 50000")
    rows = cur.fetchall()

    sql = """
        INSERT OR REPLACE INTO news
        (news_id, headline, body, published_at, source, entities, topic, sentiment, impact)
        VALUES (?, ?, NULL, ?, ?, ?, ?, ?, NULL)
    """
    batch = []
    for r in rows:
        row = dict(zip(col_list, r))
        nid = row.get("id", "")
        symbol = row.get("symbol", row.get("ticker", ""))
        date = row.get("date", row.get("published_at", row.get("created_at")))
        headline = row.get("headline", row.get("title", row.get("judul", "")))
        source = row.get("source", row.get("sumber", "idx_sentiment"))
        sentiment = row.get("sentiment", row.get("sentimen", row.get("score", 0)))
        topic = row.get("topic", row.get("kategori", None))
        news_id = f"idxs_{nid}"
        entities = to_jk(symbol) if symbol else None
        batch.append((news_id, headline, norm_date(date), source, entities, topic, to_float(sentiment)))

    if batch:
        sqlite_cur.executemany(sql, batch)
    cur.close()
    progress("idx sentiment_data → news", len(batch))
    return len(batch)


# ============================================================
# 25. IMPORT IDX_COMPLETE_DATA — technical_indicators → technical_indicators
# ============================================================
def import_idx_technical(mysql_conn, sqlite_cur):
    print("\n[25] Import idx_complete_data.technical_indicators → technical_indicators")
    cur = mysql_conn.cursor()
    cur.execute("SELECT symbol, date, sma_20, sma_50, sma_200, ema_12, ema_26, rsi_14, macd, macd_signal, macd_histogram, bollinger_upper, bollinger_middle, bollinger_lower FROM idx_complete_data.technical_indicators")
    rows = cur.fetchall()

    sql = """
        INSERT OR REPLACE INTO technical_indicators
        (ticker, date, indicator, value, timeframe, source)
        VALUES (?, ?, ?, ?, '1d', 'idx_complete')
    """
    indicators_map = {
        2: "sma_20", 3: "sma_50", 4: "sma_200",
        5: "ema_12", 6: "ema_26", 7: "rsi_14",
        8: "macd", 9: "macd_signal", 10: "macd_histogram",
        11: "bollinger_upper", 12: "bollinger_middle", 13: "bollinger_lower",
    }
    batch = []
    for r in rows:
        symbol = r[0]
        ticker = to_jk(symbol)
        date_str = norm_date(r[1])
        for idx, ind_name in indicators_map.items():
            fval = to_float(r[idx]) if idx < len(r) else None
            if fval is not None:
                batch.append((ticker, date_str, ind_name, fval))

    if batch:
        for i in range(0, len(batch), 5000):
            sqlite_cur.executemany(sql, batch[i:i+5000])
    cur.close()
    progress("idx technical_indicators", len(batch))
    return len(batch)


# ============================================================
# 26. IMPORT IDX_COMPLETE_DATA — market_indices → ohlcv
# ============================================================
def import_idx_market_indices(mysql_conn, sqlite_cur):
    print("\n[26] Import idx_complete_data.market_indices → ohlcv")
    cur = mysql_conn.cursor()
    cur.execute("SELECT GROUP_CONCAT(COLUMN_NAME) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='idx_complete_data' AND TABLE_NAME='market_indices' ORDER BY ORDINAL_POSITION")
    cols = cur.fetchone()[0]
    col_list = cols.split(",")
    print(f"  Columns: {cols}")

    cur.execute("SELECT * FROM idx_complete_data.market_indices")
    rows = cur.fetchall()

    sql = """
        INSERT OR REPLACE INTO ohlcv
        (ticker, asset_class, exchange, timestamp, timeframe, open, high, low, close, volume, adjusted_close, source, ingested_at, data_quality_score)
        VALUES (?, 'index', ?, ?, '1d', ?, ?, ?, ?, ?, ?, 'idx_complete', ?, NULL)
    """
    batch = []
    for r in rows:
        row = dict(zip(col_list, r))
        symbol = row.get("symbol", row.get("ticker", row.get("index_name", "")))
        date = row.get("date", row.get("tanggal"))
        close = row.get("close", row.get("harga"))
        o = row.get("open", row.get("open_price", close))
        h = row.get("high", row.get("high_price", close))
        l = row.get("low", row.get("low_price", close))
        v = row.get("volume", 0)
        ac = row.get("adj_close", row.get("adjusted_close", close))
        exchange = row.get("exchange", "IDX")
        if symbol and date and close is not None:
            batch.append((symbol, exchange, norm_date(date), to_float(o), to_float(h), to_float(l), to_float(close), to_float(v), to_float(ac), datetime.now().isoformat()))

    if batch:
        sqlite_cur.executemany(sql, batch)
    cur.close()
    progress("idx market_indices → ohlcv", len(batch))
    return len(batch)


# ============================================================
# 27. IMPORT IDX_COMPLETE_DATA — financial_statements → fundamental_data
# ============================================================
def import_idx_financials(mysql_conn, sqlite_cur):
    print("\n[27] Import idx_complete_data.financial_statements → fundamental_data")
    cur = mysql_conn.cursor()
    cur.execute("SELECT GROUP_CONCAT(COLUMN_NAME) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='idx_complete_data' AND TABLE_NAME='financial_statements' ORDER BY ORDINAL_POSITION")
    cols = cur.fetchone()[0]
    col_list = cols.split(",")
    print(f"  Columns: {cols}")

    cur.execute("SELECT * FROM idx_complete_data.financial_statements")
    rows = cur.fetchall()

    sql = """
        INSERT OR REPLACE INTO fundamental_data
        (ticker, date, pe_ratio, pb_ratio, roe, debt_to_equity, dividend_yield,
         earnings_per_share, book_value_per_share, net_profit, revenue,
         total_assets, total_liabilities, cash_flow, fiscal_year, quarter, source)
        VALUES (?, ?, NULL, NULL, NULL, NULL, NULL, ?, NULL, ?, ?, NULL, NULL, NULL, ?, ?, 'idx_complete')
    """
    batch = []
    for r in rows:
        row = dict(zip(col_list, r))
        symbol = row.get("symbol", row.get("ticker", ""))
        ticker = to_jk(symbol)
        date = row.get("date", row.get("period", row.get("fiscal_year")))
        eps = row.get("eps", row.get("earnings_per_share"))
        revenue = row.get("revenue", row.get("total_revenue"))
        net_profit = row.get("net_profit", row.get("net_income"))
        fy = row.get("fiscal_year", row.get("year"))
        q = row.get("quarter")
        if ticker and date:
            batch.append((ticker, str(date), to_float(eps), to_float(net_profit), to_float(revenue), fy, q))

    if batch:
        sqlite_cur.executemany(sql, batch)
    cur.close()
    progress("idx financial_statements → fundamental_data", len(batch))
    return len(batch)


# ============================================================
# 28. IMPORT IDX_COMPLETE_DATA — dividends → dividends
# ============================================================
def import_idx_dividends(mysql_conn, sqlite_cur):
    print("\n[28] Import idx_complete_data.dividends → dividends")
    cur = mysql_conn.cursor()
    cur.execute("SELECT GROUP_CONCAT(COLUMN_NAME) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='idx_complete_data' AND TABLE_NAME='dividends' ORDER BY ORDINAL_POSITION")
    cols = cur.fetchone()[0]
    col_list = cols.split(",")
    print(f"  Columns: {cols}")

    cur.execute("SELECT * FROM idx_complete_data.dividends")
    rows = cur.fetchall()

    sql = """
        INSERT OR REPLACE INTO dividends
        (ticker, ex_date, record_date, payment_date, amount, currency, frequency, source)
        VALUES (?, ?, ?, ?, ?, 'IDR', ?, 'idx_complete')
    """
    batch = []
    for r in rows:
        row = dict(zip(col_list, r))
        symbol = row.get("symbol", row.get("ticker", ""))
        ticker = to_jk(symbol)
        ex_date = norm_date(row.get("ex_date", row.get("date", row.get("ex_dividend_date"))))
        record_date = norm_date(row.get("record_date"))
        payment_date = norm_date(row.get("payment_date", row.get("pay_date")))
        amount = row.get("amount", row.get("dividend_amount", row.get("amount_per_share")))
        freq = row.get("frequency", row.get("type", ""))
        if ticker and ex_date and amount is not None:
            batch.append((ticker, ex_date, record_date, payment_date, to_float(amount), freq))

    if batch:
        sqlite_cur.executemany(sql, batch)
    cur.close()
    progress("idx dividends → dividends", len(batch))
    return len(batch)


# ============================================================
# 29. IMPORT PARQUET — sqlite_ohlcv → ohlcv (supplement)
# ============================================================
def import_parquet_sqlite_ohlcv(sqlite_cur):
    print("\n[29] Import Parquet sqlite_ohlcv → ohlcv")
    import pyarrow.parquet as pq

    fp = os.path.join(PARQUET_DIR, "sqlite_ohlcv", "sqlite_ohlcv.parquet")
    if not os.path.exists(fp):
        print("  File not found, skipping")
        return 0

    df = pq.read_table(fp).to_pandas()
    print(f"  Rows: {len(df)}")

    sql = """
        INSERT OR REPLACE INTO ohlcv
        (ticker, asset_class, exchange, timestamp, timeframe, open, high, low, close, volume, adjusted_close, source, ingested_at, data_quality_score)
        VALUES (?, 'equity', 'IDX', ?, '1d', ?, ?, ?, ?, ?, ?, 'parquet_sqlite', ?, NULL)
    """
    batch = []
    for _, row in df.iterrows():
        ticker = row.get("ticker", "")
        if ticker and not ticker.endswith(".JK") and "." not in ticker and not ticker.startswith("^"):
            ticker = f"{ticker}.JK"
        ts = str(row.get("date", row.get("timestamp", "")))[:10]
        o = row.get("open")
        h = row.get("high")
        l = row.get("low")
        c = row.get("close")
        v = row.get("volume", 0)
        ac = row.get("adj_close", row.get("adjusted_close", c))
        if ticker and ts:
            batch.append((ticker, ts, to_float(o), to_float(h), to_float(l), to_float(c), to_float(v), to_float(ac), datetime.now().isoformat()))

    if batch:
        for i in range(0, len(batch), 5000):
            sqlite_cur.executemany(sql, batch[i:i+5000])
    progress("parquet sqlite_ohlcv", len(batch))
    return len(batch)


# ============================================================
# 30. IMPORT PARQUET — sqlite_global_market_data → ohlcv
# ============================================================
def import_parquet_global_market(sqlite_cur):
    print("\n[30] Import Parquet sqlite_global_market_data → ohlcv")
    import pyarrow.parquet as pq

    fp = os.path.join(PARQUET_DIR, "sqlite_global_market_data", "sqlite_global_market_data.parquet")
    if not os.path.exists(fp):
        print("  File not found, skipping")
        return 0

    df = pq.read_table(fp).to_pandas()
    print(f"  Rows: {len(df)}")

    sql = """
        INSERT OR REPLACE INTO ohlcv
        (ticker, asset_class, exchange, timestamp, timeframe, open, high, low, close, volume, adjusted_close, source, ingested_at, data_quality_score)
        VALUES (?, 'index', 'GLOBAL', ?, '1d', ?, ?, ?, ?, ?, ?, 'parquet_sqlite', ?, NULL)
    """
    batch = []
    for _, row in df.iterrows():
        ticker = row.get("ticker", "")
        ts = str(row.get("date", ""))[:10]
        o = row.get("open")
        h = row.get("high")
        l = row.get("low")
        c = row.get("close")
        v = row.get("volume", 0)
        ac = row.get("adj_close", row.get("adjusted_close", c))
        if ticker and ts:
            batch.append((ticker, ts, to_float(o), to_float(h), to_float(l), to_float(c), to_float(v), to_float(ac), datetime.now().isoformat()))

    if batch:
        for i in range(0, len(batch), 5000):
            sqlite_cur.executemany(sql, batch[i:i+5000])
    progress("parquet global_market_data", len(batch))
    return len(batch)


# ============================================================
# 31. IMPORT PARQUET — sqlite_macro_data → macro_data
# ============================================================
def import_parquet_macro(sqlite_cur):
    print("\n[31] Import Parquet sqlite_macro_data → macro_data")
    import pyarrow.parquet as pq

    fp = os.path.join(PARQUET_DIR, "sqlite_macro_data", "sqlite_macro_data.parquet")
    if not os.path.exists(fp):
        print("  File not found, skipping")
        return 0

    df = pq.read_table(fp).to_pandas()
    print(f"  Rows: {len(df)}")

    sql = "INSERT OR REPLACE INTO macro_data VALUES (?, ?, ?, ?, 'parquet_sqlite', ?)"
    batch = []
    for _, row in df.iterrows():
        series_id = row.get("series_id", "")
        date = str(row.get("date", ""))[:10]
        value = row.get("value")
        region = row.get("region", "")
        category = row.get("category", "")
        freq = row.get("frequency", "daily")
        if series_id and date and value is not None:
            unit = f"{category}_{region}" if region else category
            batch.append((series_id, date, to_float(value), unit, freq))

    if batch:
        for i in range(0, len(batch), 5000):
            sqlite_cur.executemany(sql, batch[i:i+5000])
    progress("parquet macro_data", len(batch))
    return len(batch)


# ============================================================
# 32. IMPORT PARQUET — multi_asset → ohlcv
# ============================================================
def import_parquet_multi_asset(sqlite_cur):
    print("\n[32] Import Parquet multi_asset → ohlcv")
    import pyarrow.parquet as pq

    multi_dir = os.path.join(PARQUET_DIR, "multi_asset")
    if not os.path.isdir(multi_dir):
        print("  Dir not found, skipping")
        return 0

    files = [f for f in os.listdir(multi_dir) if f.endswith(".parquet")]
    print(f"  Files: {len(files)}")

    sql = """
        INSERT OR REPLACE INTO ohlcv
        (ticker, asset_class, exchange, timestamp, timeframe, open, high, low, close, volume, adjusted_close, source, ingested_at, data_quality_score)
        VALUES (?, ?, 'GLOBAL', ?, '1d', ?, ?, ?, ?, ?, ?, 'parquet_multi_asset', ?, NULL)
    """
    total = 0
    for f in files:
        fp = os.path.join(multi_dir, f)
        try:
            df = pq.read_table(fp).to_pandas()
        except Exception as e:
            print(f"  ERROR reading {f}: {e}")
            continue

        batch = []
        for _, row in df.iterrows():
            kode = row.get("kode", row.get("ticker", ""))
            tanggal = row.get("tanggal", row.get("date", ""))
            harga = row.get("harga", row.get("close", row.get("price")))
            if kode and str(tanggal) and harga is not None:
                asset_class = "commodity"
                if "forex" in str(f).lower() or "usd" in str(kode).lower():
                    asset_class = "forex"
                elif "index" in str(f).lower():
                    asset_class = "index"
                batch.append((kode, asset_class, str(tanggal)[:10], to_float(harga), to_float(harga), to_float(harga), to_float(harga), 0, to_float(harga), datetime.now().isoformat()))

        if batch:
            sqlite_cur.executemany(sql, batch)
            total += len(batch)

    progress("parquet multi_asset", total)
    return total


# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 70)
    print("IMPORT DATA LENGKAP: MySQL + Parquet → SQLite trading_system.db")
    print("=" * 70)
    start_time = time.time()

    # Check pymysql
    try:
        import pymysql
    except ImportError:
        print("Installing pymysql...")
        os.system(f"{sys.executable} -m pip install pymysql -q")
        import pymysql

    # Backup DB
    backup_path = str(DB_PATH).replace(".db", "_backup_pre_import.db")
    print(f"\nBackup: {DB_PATH} → {backup_path}")
    import shutil
    shutil.copy2(str(DB_PATH), backup_path)

    # Connect
    print("\nConnecting to MySQL...")
    mysql_conn = get_mysql_conn()
    print("  Connected!")

    sqlite_conn = sqlite3.connect(str(DB_PATH))
    sqlite_conn.execute("PRAGMA journal_mode=WAL")
    sqlite_conn.execute("PRAGMA synchronous=NORMAL")
    sqlite_conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
    sqlite_cur = sqlite_conn.cursor()

    # Run all imports
    results = {}

    # --- MySQL data_pasar_modal ---
    results["stock_history"] = import_stock_history(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    results["saham"] = import_saham(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    results["saham_fundamental"] = import_fundamental(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    results["saham_snapshot"] = import_snapshots(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    results["broker_flow"] = import_broker_flow(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    results["dividends"] = import_dividends(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    results["corporate_actions"] = import_corporate_actions(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    results["indikator_teknikal"] = import_technical_indicators(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    results["berita_sentimen"] = import_sentiment_news(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    results["fear_greed"] = import_fear_greed(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    results["makroekonomi"] = import_macro(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    results["komoditas"] = import_commodity(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    results["ihsg"] = import_ihsg(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    results["bursa_global"] = import_global_indices(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    results["multi_asset"] = import_multi_asset(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    results["stock_personality"] = import_stock_personality(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    results["valuation_cache"] = import_valuation(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    results["chart_patterns"] = import_chart_patterns(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    results["policy_events"] = import_policy_events(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    results["external_events"] = import_external_events(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    results["esg_scores"] = import_esg(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    results["corporate_governance"] = import_corp_governance(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    # --- MySQL idx_complete_data ---
    results["idx_daily_prices"] = import_idx_daily_prices(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    results["idx_sentiment"] = import_idx_sentiment(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    results["idx_technical"] = import_idx_technical(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    results["idx_market_indices"] = import_idx_market_indices(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    results["idx_financials"] = import_idx_financials(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    results["idx_dividends"] = import_idx_dividends(mysql_conn, sqlite_cur)
    sqlite_conn.commit()

    # --- Parquet ---
    results["parquet_sqlite_ohlcv"] = import_parquet_sqlite_ohlcv(sqlite_cur)
    sqlite_conn.commit()

    results["parquet_global_market"] = import_parquet_global_market(sqlite_cur)
    sqlite_conn.commit()

    results["parquet_macro"] = import_parquet_macro(sqlite_cur)
    sqlite_conn.commit()

    results["parquet_multi_asset"] = import_parquet_multi_asset(sqlite_cur)
    sqlite_conn.commit()

    # Final commit
    sqlite_conn.commit()

    # Summary
    elapsed = time.time() - start_time
    print("\n" + "=" * 70)
    print("IMPORT SUMMARY")
    print("=" * 70)
    total_rows = 0
    for name, count in results.items():
        print(f"  {name:<35} {count:>12,} rows")
        total_rows += count
    print(f"  {'─' * 50}")
    print(f"  {'TOTAL':<35} {total_rows:>12,} rows")
    print(f"\n  Elapsed: {elapsed:.1f}s")
    print(f"  DB size: {os.path.getsize(str(DB_PATH)) / 1024 / 1024:.1f} MB")

    # Verify table counts
    print("\nFinal table counts:")
    sqlite_cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    for (t,) in sqlite_cur.fetchall():
        sqlite_cur.execute(f'SELECT COUNT(*) FROM "{t}"')
        cnt = sqlite_cur.fetchone()[0]
        if cnt > 0:
            print(f"  {t:<35} {cnt:>12,}")

    mysql_conn.close()
    sqlite_conn.close()
    print(f"\nDone! Backup at: {backup_path}")


if __name__ == "__main__":
    main()
