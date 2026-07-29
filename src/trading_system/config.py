"""Konfigurasi global untuk sistem trading."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RAW_ZONE = DATA_DIR / "raw"
CLEAN_ZONE = DATA_DIR / "clean"
DB_PATH = DATA_DIR / "trading_system.db"

DEFAULT_BENCHMARK = "^JKSE"  # IHSG
DEFAULT_BROKER_FEE_BUY = 0.0015       # 0.15% beli
DEFAULT_BROKER_FEE_SELL = 0.0025      # 0.15% broker + 0.1% PPh
DEFAULT_LEVY = 0.0000043              # 0.00043% levy bursa
DEFAULT_SLIPPAGE = 0.0005             # 0.05% slippage default
DEFAULT_TIMEZONE = "Asia/Jakarta"

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
