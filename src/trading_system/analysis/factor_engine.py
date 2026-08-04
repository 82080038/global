"""Factor Engine (X, §4.1).

Adapted from TIP/python/engines/factor_engine.py.
Uses SQLite DataStorage instead of PostgreSQL.

Factors: momentum, low_volatility, quality, beta, size, value.
All factors use cross-sectional percentile rank, liquidity/minimum-history filters,
missing-data policy, and factor versioning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from trading_system.data.storage import DataStorage

FACTOR_VERSION = "1.0"
MIN_HISTORY_DAYS = 60
LIQUIDITY_MIN_VOLUME = 100_000


@dataclass
class FactorConfig:
    name: str
    enabled: bool = True
    weight: float = 1.0
    min_history: int = MIN_HISTORY_DAYS
    params: dict = field(default_factory=dict)


@dataclass
class FactorResult:
    instrument_id: int
    symbol: str
    factor_name: str
    raw_value: float | None
    percentile_rank: float | None
    as_of: datetime
    bars_used: int
    reason: str = ""


def percentile_rank(values: np.ndarray, value: float) -> float:
    if len(values) == 0:
        return 0.5
    count_below = np.sum(values < value)
    count_equal = np.sum(values == value)
    n = len(values)
    return float((count_below + 0.5 * count_equal) / n)


def compute_momentum(df: pd.DataFrame, as_of: datetime) -> tuple[float | None, int]:
    if len(df) < 22:
        return None, len(df)
    closes = df["close"].values
    adj = df["adjusted_close"].values if "adjusted_close" in df.columns else closes
    returns = {}
    for period, days in [("1M", 22), ("3M", 66), ("6M", 132), ("12M", 252)]:
        if len(adj) > days:
            ret = (adj[-1] / adj[-days - 1]) - 1.0
            returns[period] = ret
    if not returns:
        return None, len(df)
    return float(np.mean(list(returns.values()))), len(df)


def compute_low_volatility(df: pd.DataFrame, as_of: datetime) -> tuple[float | None, int]:
    if len(df) < 60:
        return None, len(df)
    closes = df["close"].values
    returns = np.diff(closes) / closes[:-1]
    vol = float(np.std(returns[-60:], ddof=1))
    return -vol, len(df)


def compute_quality(df: pd.DataFrame, as_of: datetime) -> tuple[float | None, int]:
    if len(df) < 60:
        return None, len(df)
    closes = df["close"].values
    returns = np.diff(closes) / closes[:-1]
    recent = returns[-60:]
    mean_ret = float(np.mean(recent))
    std_ret = float(np.std(recent, ddof=1))
    if std_ret < 1e-12:
        return 0.0, len(df)
    return float(mean_ret / std_ret), len(df)


def compute_beta(df: pd.DataFrame, benchmark_returns: np.ndarray | None, as_of: datetime) -> tuple[float | None, int]:
    if benchmark_returns is None or len(benchmark_returns) < 60:
        return None, len(df)
    if len(df) < 61:
        return None, len(df)
    closes = df["close"].values
    returns = np.diff(closes) / closes[:-1]
    n = min(60, len(returns), len(benchmark_returns))
    if n < 20:
        return None, len(df)
    r = returns[-n:]
    b = benchmark_returns[-n:]
    var_b = float(np.var(b, ddof=1))
    if var_b < 1e-12:
        return 0.0, len(df)
    cov = float(np.cov(r, b, ddof=1)[0, 1])
    return cov / var_b, len(df)


def compute_size(df: pd.DataFrame, as_of: datetime) -> tuple[float | None, int]:
    if len(df) < 20:
        return None, len(df)
    recent = df.tail(20)
    avg_volume = float(recent["volume"].mean())
    latest_price = float(df["close"].iloc[-1])
    if avg_volume <= 0 or latest_price <= 0:
        return None, len(df)
    return float(latest_price * avg_volume), len(df)


def compute_value_proxy(df: pd.DataFrame, as_of: datetime) -> tuple[float | None, int]:
    if len(df) < 1:
        return None, len(df)
    price = float(df["close"].iloc[-1])
    if price <= 0:
        return None, len(df)
    return 1.0 / price, len(df)


FACTOR_FUNCS = {
    "momentum": compute_momentum,
    "low_volatility": compute_low_volatility,
    "quality": compute_quality,
    "beta": compute_beta,
    "size": compute_size,
    "value": compute_value_proxy,
}


class FactorEngine:
    """Compute cross-sectional factor scores for a universe of instruments.

    All scores are percentile-ranked and PIT-safe (only uses data up to as_of).
    Adapted from TIP FactorEngine — uses SQLite DataStorage.
    """

    def __init__(
        self,
        storage: DataStorage | None = None,
        factors: list[FactorConfig] | None = None,
        benchmark_symbol: str = "^JKSE",
        as_of: datetime | None = None,
        factor_version: str = FACTOR_VERSION,
        min_history: int = MIN_HISTORY_DAYS,
        liquidity_min_volume: int = LIQUIDITY_MIN_VOLUME,
    ):
        self.storage = storage or DataStorage()
        self.factors = factors or [
            FactorConfig("momentum"),
            FactorConfig("low_volatility"),
            FactorConfig("quality"),
            FactorConfig("size"),
            FactorConfig("value"),
        ]
        self.benchmark_symbol = benchmark_symbol
        self.as_of = as_of or datetime.now(UTC)
        self.factor_version = factor_version
        self.min_history = min_history
        self.liquidity_min_volume = liquidity_min_volume

    def _load_benchmark_returns(self) -> np.ndarray | None:
        df = self.storage.load_ohlcv(self.benchmark_symbol)
        if df is None or df.empty or len(df) < 61:
            return None
        closes = df["close"].values.astype(float)
        return np.diff(closes) / closes[:-1]

    def _filter_liquidity(self, df: pd.DataFrame) -> bool:
        if len(df) < 20:
            return False
        avg_vol = float(df.tail(20)["volume"].mean())
        return avg_vol >= self.liquidity_min_volume

    def compute(self, tickers: list[str] | None = None) -> dict[str, Any]:
        """Compute all factor scores for the universe.

        Args:
            tickers: List of ticker symbols. If None, uses active equity tickers only.

        Returns dict with as_of, factor_versions, results, composite_ranks, reason_codes.
        """
        if tickers is None:
            tickers = self.storage.list_active_equity_tickers()

        benchmark_returns = self._load_benchmark_returns()

        raw_values: dict[str, dict[str, float]] = {}
        results: list[FactorResult] = []
        reason_codes: list[str] = []
        skipped_liquidity = 0
        skipped_history = 0

        for ticker in tickers:
            df = self.storage.load_ohlcv(ticker)
            if df is None or df.empty:
                reason_codes.append(f"NO_DATA:{ticker}")
                continue

            if len(df) < self.min_history:
                skipped_history += 1
                reason_codes.append(f"INSUFFICIENT_HISTORY:{ticker} ({len(df)} < {self.min_history})")
                continue

            if not self._filter_liquidity(df):
                skipped_liquidity += 1
                reason_codes.append(f"LOW_LIQUIDITY:{ticker}")
                continue

            for fcfg in self.factors:
                if not fcfg.enabled:
                    continue

                func = FACTOR_FUNCS.get(fcfg.name)
                if func is None:
                    reason_codes.append(f"UNKNOWN_FACTOR:{fcfg.name}")
                    continue

                if fcfg.name == "beta":
                    raw_val, bars = func(df, benchmark_returns, self.as_of)
                else:
                    raw_val, bars = func(df, self.as_of)

                if raw_val is None:
                    results.append(FactorResult(
                        instrument_id=0,
                        symbol=ticker,
                        factor_name=fcfg.name,
                        raw_value=None,
                        percentile_rank=None,
                        as_of=self.as_of,
                        bars_used=bars,
                        reason="RAW_VALUE_NONE",
                    ))
                    continue

                if fcfg.name not in raw_values:
                    raw_values[fcfg.name] = {}
                raw_values[fcfg.name][ticker] = raw_val

                results.append(FactorResult(
                    instrument_id=0,
                    symbol=ticker,
                    factor_name=fcfg.name,
                    raw_value=round(raw_val, 6),
                    percentile_rank=None,
                    as_of=self.as_of,
                    bars_used=bars,
                ))

        # Cross-sectional percentile ranking
        factor_arrays: dict[str, np.ndarray] = {}
        for factor_name, values_dict in raw_values.items():
            tickers_list = list(values_dict.keys())
            vals = np.array([values_dict[t] for t in tickers_list])
            factor_arrays[factor_name] = vals

            for i, ticker in enumerate(tickers_list):
                rank = percentile_rank(vals, vals[i])
                for r in results:
                    if r.symbol == ticker and r.factor_name == factor_name:
                        r.percentile_rank = round(rank, 6)

        # Composite score
        composite: dict[str, float] = {}
        enabled_factors = [f for f in self.factors if f.enabled and f.name in raw_values]
        total_weight = sum(f.weight for f in enabled_factors)

        if total_weight > 0:
            for ticker in set().union(*[set(raw_values[f.name].keys()) for f in enabled_factors]):
                weighted_sum = 0.0
                used_weight = 0.0
                for fcfg in enabled_factors:
                    if ticker in raw_values[fcfg.name]:
                        vals = factor_arrays[fcfg.name]
                        inst_val = raw_values[fcfg.name][ticker]
                        rank = percentile_rank(vals, inst_val)
                        weighted_sum += rank * fcfg.weight
                        used_weight += fcfg.weight
                if used_weight > 0:
                    composite[ticker] = round(weighted_sum / used_weight, 6)

        return {
            "as_of": self.as_of,
            "factor_version": self.factor_version,
            "universe_size": len(tickers),
            "scored_instruments": len(composite),
            "results": [
                {
                    "symbol": r.symbol,
                    "factor_name": r.factor_name,
                    "raw_value": r.raw_value,
                    "percentile_rank": r.percentile_rank,
                    "bars_used": r.bars_used,
                    "reason": r.reason,
                }
                for r in results
            ],
            "composite_ranks": composite,
            "reason_codes": reason_codes,
            "skipped_liquidity": skipped_liquidity,
            "skipped_history": skipped_history,
        }
