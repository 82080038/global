"""Konfigurasi global untuk sistem trading."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RAW_ZONE = DATA_DIR / "raw"
CLEAN_ZONE = DATA_DIR / "clean"
DB_PATH = DATA_DIR / "trading_system.db"

# Archive zone untuk data raw permanen (Parquet).
# Default: subfolder di dalam data/, bisa di-override ke external HDD via env.
# Contoh: DATA_ARCHIVE_DIR=K:\trading_data\raw
DATA_ARCHIVE_DIR = Path(os.getenv("DATA_ARCHIVE_DIR", str(DATA_DIR / "archive")))

DEFAULT_BENCHMARK = "^JKSE"  # IHSG
DEFAULT_BROKER_FEE_BUY = 0.0015       # 0.15% beli
DEFAULT_BROKER_FEE_SELL = 0.0025      # 0.15% broker + 0.1% PPh
DEFAULT_LEVY = 0.0000043              # 0.00043% levy bursa
DEFAULT_SLIPPAGE = 0.0005             # 0.05% slippage default
DEFAULT_TIMEZONE = "Asia/Jakarta"

# IDX market conventions (§3.1 SARAN_PENGEMBANGAN.md)
IDX_LOT_SIZE = 100  # 1 lot = 100 lembar di Bursa Efek Indonesia


def idx_tick_size(price: float) -> float:
    """Tick size IDX berdasarkan fraksi harga (Peraturan BEI)."""
    if price < 200:
        return 1.0
    elif price < 500:
        return 2.0
    elif price < 2000:
        return 5.0
    elif price < 5000:
        return 10.0
    else:
        return 25.0


def round_to_tick(price: float) -> float:
    """Bulatkan harga ke tick size IDX terdekat."""
    tick = idx_tick_size(price)
    return round(price / tick) * tick

# Satu sumber kebenaran untuk modal trading (§3.3 SARAN_PENGEMBANGAN.md).
# Semua engine (risk, decision, execution, backtest CLI, API) HARUS membaca
# nilai ini alih-alih hard-code angka modal sendiri-sendiri.
TRADING_CAPITAL = float(os.getenv("TRADING_CAPITAL", "100000000"))

# Ambang konviksi di bawah mana posisi terbuka harus di-exit (SELL), meskipun
# harga belum menyentuh stop-loss/take-profit (§2.3 SARAN_PENGEMBANGAN.md).
EXIT_CONVICTION_THRESHOLD = float(os.getenv("EXIT_CONVICTION_THRESHOLD", "40"))

# YFinance rate limiting
YFINANCE_RATE_LIMIT_CALLS = 1
YFINANCE_RATE_LIMIT_WINDOW = 1.0  # seconds

# Macro & Global proxy instruments (Yahoo Finance)
DEFAULT_MACRO_TICKERS = {
    "US10Y": "^TNX",          # US Treasury 10Y yield
    "GOLD": "GC=F",
    "OIL": "CL=F",
    "USD_IDR": "IDR=X",       # USD/IDR
    "DXY": "DX-Y.NYB",        # US Dollar Index
}

DEFAULT_GLOBAL_TICKERS = {
    "SP500": "^GSPC",
    "NASDAQ": "^IXIC",
    "DOW": "^DJI",
    "HANGSENG": "^HSI",
    "NIKKEI": "^N225",
    "FTSE": "^FTSE",
    "DAX": "^GDAXI",
}

def ensure_dirs():
    RAW_ZONE.mkdir(parents=True, exist_ok=True)
    CLEAN_ZONE.mkdir(parents=True, exist_ok=True)
    DATA_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
