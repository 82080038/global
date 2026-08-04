"""Database Seeder — mengisi data awal untuk testing & demo.

Menyuntikkan OHLCV sintetis untuk ticker Indonesia (BBCA.JK, TLKM.JK, ASII.JK)
dan ticker global/macro, plus source_health dan sample scores.

Usage:
    python -m trading_system.data.seeder
"""

from __future__ import annotations

import random
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from trading_system.config import (
    DEFAULT_BENCHMARK,
    DEFAULT_GLOBAL_TICKERS,
    DEFAULT_MACRO_TICKERS,
    ensure_dirs,
)
from trading_system.data.storage import DataStorage

SEED_TICKERS = {
    "BBCA.JK": {"base_price": 8000, "drift": 0.0004, "vol": 0.015, "exchange": "IDX"},
    "TLKM.JK": {"base_price": 2800, "drift": 0.0001, "vol": 0.012, "exchange": "IDX"},
    "ASII.JK": {"base_price": 5200, "drift": -0.0002, "vol": 0.018, "exchange": "IDX"},
    "BMRI.JK": {"base_price": 9500, "drift": 0.0003, "vol": 0.014, "exchange": "IDX"},
    "GOTO.JK": {"base_price": 60, "drift": -0.001, "vol": 0.025, "exchange": "IDX"},
}

ALL_TICKERS = {
    **SEED_TICKERS,
    DEFAULT_BENCHMARK: {"base_price": 7000, "drift": 0.0003, "vol": 0.013, "exchange": "IDX"},
    **{t: {"base_price": 100, "drift": 0.0002, "vol": 0.011, "exchange": "GLOBAL"} for t in DEFAULT_GLOBAL_TICKERS.values()},
    **{t: {"base_price": 50, "drift": 0.0001, "vol": 0.010, "exchange": "GLOBAL"} for t in DEFAULT_MACRO_TICKERS.values()},
}


def _generate_ohlcv(ticker: str, config: dict, days: int = 500) -> pd.DataFrame:
    """Generate synthetic OHLCV using geometric brownian motion."""
    seed_val = sum(ord(c) for c in ticker)
    random.seed(seed_val)
    np.random.seed(seed_val)

    base = config["base_price"]
    drift = config["drift"]
    vol = config["vol"]

    dates = pd.bdate_range(end=datetime.now(UTC).date(), periods=days)
    returns = np.random.normal(drift, vol, size=days)
    prices = base * np.exp(np.cumsum(returns))

    records = []
    for i, dt in enumerate(dates):
        close = round(float(prices[i]), 2)
        daily_vol = abs(np.random.normal(0, vol)) * base * 1_000_000
        volume = max(100_000, int(daily_vol))
        high = round(close * (1 + abs(np.random.normal(0, vol * 0.5))), 2)
        low = round(close * (1 - abs(np.random.normal(0, vol * 0.5))), 2)
        op = round(close * (1 + np.random.normal(0, vol * 0.3)), 2)
        records.append({
            "ticker": ticker,
            "asset_class": "equity" if ticker.endswith(".JK") else "index",
            "exchange": config["exchange"],
            "timestamp": dt.strftime("%Y-%m-%d"),
            "timeframe": "1d",
            "open": op,
            "high": max(high, op, close),
            "low": min(low, op, close),
            "close": close,
            "volume": volume,
            "adjusted_close": close,
            "source": "seeder",
            "ingested_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            "data_quality_score": 100.0,
        })
    return pd.DataFrame(records)


def _generate_scores(storage: DataStorage, ticker: str):
    """Generate sample analysis scores for a ticker."""
    engines = {
        "technical": lambda: random.uniform(30, 85),
        "fundamental": lambda: random.uniform(25, 80),
        "macro": lambda: random.uniform(35, 75),
        "global": lambda: random.uniform(30, 70),
        "relationship": lambda: random.uniform(20, 65),
        "sentiment": lambda: random.uniform(30, 80),
    }
    for engine_name, score_fn in engines.items():
        score = round(score_fn(), 2)
        breakdown = {"seed": True, "value": score}
        storage.save_score(ticker, engine_name, score, breakdown)


def seed_database(db_path=None):
    """Seed the entire database with synthetic data."""
    ensure_dirs()
    storage = DataStorage(db_path) if db_path else DataStorage()

    print("Seeding OHLCV data...")
    for ticker, config in ALL_TICKERS.items():
        df = _generate_ohlcv(ticker, config)
        count = storage.save_ohlcv(df)
        storage.update_source_health(f"yfinance_{ticker}", "ok", True)
        print(f"  {ticker}: {count} rows")

    print("Seeding source_health...")
    storage.update_source_health("yfinance", "ok", True)
    storage.update_source_health("yahoo_finance_api", "ok", True)

    print("Seeding scores...")
    for ticker in SEED_TICKERS:
        _generate_scores(storage, ticker)
        print(f"  {ticker}: 6 engine scores")

    print("Seeding audit log...")
    storage.audit("seeder.run", {"timestamp": datetime.now(UTC).isoformat(), "action": "seed"})

    print(f"\nDatabase seeded successfully: {storage.db_path}")
    print(f"  Tickers: {len(storage.list_tickers())}")
    print(f"  Scores: {len(storage.load_scores())}")


if __name__ == "__main__":
    seed_database()
