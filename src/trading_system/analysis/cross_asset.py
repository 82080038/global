"""Cross-Asset Engine (AA, §4.1).

Adapted from TIP/python/engines/cross_asset.py.
Uses SQLite DataStorage instead of PostgreSQL.

Computes rolling beta, correlation, z-scores, and risk-on/off consistency
across asset classes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np

from trading_system.data.storage import DataStorage

CONFIG_VERSION = "1.0"

DEFAULT_PAIRS = [
    {"target": "sp500", "benchmark": "dxy", "label": "SP500_vs_DXY"},
    {"target": "sp500", "benchmark": "vix", "label": "SP500_vs_VIX"},
    {"target": "jkse", "benchmark": "dxy", "label": "JKSE_vs_DXY"},
    {"target": "jkse", "benchmark": "usdidr", "label": "JKSE_vs_USDIDR"},
    {"target": "jkse", "benchmark": "vix", "label": "JKSE_vs_VIX"},
]

ROLLING_WINDOW = 30
LOOKBACK = 60

# Symbol mapping for SQLite storage
SYMBOL_MAP = {
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "nikkei": "^N225",
    "hangseng": "^HSI",
    "dxy": "DX-Y.NYB",
    "vix": "^VIX",
    "usdidr": "USDIDR=X",
    "jkse": "^JKSE",
    "us_10y": "^TNX",
    "us_2y": "^IRX",
}


class CrossAssetEngine:
    """Compute cross-asset rolling beta, correlation, z-scores, and
    risk-on/off consistency. Adapted from TIP — uses SQLite DataStorage.
    """

    DEFAULT_PAIRS = DEFAULT_PAIRS

    def __init__(
        self,
        storage: DataStorage | None = None,
        pairs: list[dict[str, Any]] | None = None,
        rolling_window: int = ROLLING_WINDOW,
        config_version: str = CONFIG_VERSION,
        as_of: datetime | None = None,
    ):
        self.storage = storage or DataStorage()
        self.pairs = pairs or self.DEFAULT_PAIRS
        self.rolling_window = rolling_window
        self.config_version = config_version
        self.as_of = as_of or datetime.now(UTC)

    def _load_returns(self, key: str) -> tuple[list, np.ndarray, np.ndarray] | None:
        symbol = SYMBOL_MAP.get(key, key)
        df = self.storage.load_ohlcv(symbol)
        if df is None or df.empty or len(df) < 3:
            return None
        df = df.sort_index()
        closes = df["close"].values.astype(float)
        returns = np.diff(closes) / closes[:-1]
        times = list(df.index)
        return times, closes, returns

    def _rolling_beta(self, target_returns: np.ndarray, bench_returns: np.ndarray) -> float:
        n = min(self.rolling_window, len(target_returns), len(bench_returns))
        if n < 5:
            return 0.0
        t = target_returns[-n:]
        b = bench_returns[-n:]
        var_b = np.var(b, ddof=1)
        if var_b < 1e-12:
            return 0.0
        cov = np.cov(t, b, ddof=1)[0, 1]
        return float(cov / var_b)

    def _rolling_corr(self, target_returns: np.ndarray, bench_returns: np.ndarray) -> float:
        n = min(self.rolling_window, len(target_returns), len(bench_returns))
        if n < 5:
            return 0.0
        t = target_returns[-n:]
        b = bench_returns[-n:]
        if np.std(t) < 1e-12 or np.std(b) < 1e-12:
            return 0.0
        return float(np.corrcoef(t, b)[0, 1])

    def _zscore(self, returns: np.ndarray) -> float:
        if len(returns) < 2:
            return 0.0
        historical = returns[:-1]
        mean = float(np.mean(historical))
        std = float(np.std(historical, ddof=1))
        if std < 1e-12:
            return 0.0
        return float((returns[-1] - mean) / std)

    def compute(self) -> dict[str, Any]:
        series_cache: dict[str, tuple] = {}
        pair_results = []
        reason_codes: list[str] = []
        latest_date = None

        for pair in self.pairs:
            target_key = pair["target"]
            bench_key = pair["benchmark"]
            label = pair["label"]

            if target_key not in series_cache:
                series_cache[target_key] = self._load_returns(target_key)
            if bench_key not in series_cache:
                series_cache[bench_key] = self._load_returns(bench_key)

            target_data = series_cache[target_key]
            bench_data = series_cache[bench_key]

            if target_data is None or bench_data is None:
                reason_codes.append(f"SKIP:{label} (data tidak tersedia)")
                continue

            _, _, t_returns = target_data
            b_times, _, b_returns = bench_data

            min_len = min(len(t_returns), len(b_returns))
            if min_len < 5:
                reason_codes.append(f"SKIP:{label} (data terlalu pendek: {min_len})")
                continue

            t_aligned = t_returns[-min_len:]
            b_aligned = b_returns[-min_len:]

            beta = self._rolling_beta(t_aligned, b_aligned)
            corr = self._rolling_corr(t_aligned, b_aligned)
            target_z = self._zscore(t_aligned)
            bench_z = self._zscore(b_aligned)

            pair_results.append({
                "label": label,
                "target": target_key,
                "benchmark": bench_key,
                "beta": round(beta, 4),
                "correlation": round(corr, 4),
                "target_z": round(target_z, 4),
                "benchmark_z": round(bench_z, 4),
            })

            if latest_date is None:
                latest_date = b_times[-1]

        risk_on_votes = 0
        risk_off_votes = 0
        total_votes = 0

        for pr in pair_results:
            target_z = pr["target_z"]
            bench_key = pr["benchmark"]
            corr = pr["correlation"]

            if bench_key in ("dxy", "vix", "usdidr"):
                if target_z > 0 and corr < 0:
                    risk_on_votes += 1
                elif target_z < 0 and corr < 0:
                    risk_off_votes += 1
                total_votes += 1
            elif bench_key in ("us_10y", "us_2y"):
                if target_z > 0:
                    risk_on_votes += 1
                elif target_z < 0:
                    risk_off_votes += 1
                total_votes += 1

        consistency = 0.0
        regime = "neutral"
        if total_votes > 0:
            if risk_on_votes > risk_off_votes:
                consistency = risk_on_votes / total_votes
                regime = "risk_on"
            elif risk_off_votes > risk_on_votes:
                consistency = risk_off_votes / total_votes
                regime = "risk_off"
            else:
                consistency = 0.5
                regime = "neutral"

        reason_codes.append(
            f"CROSS_ASSET_REGIME:{regime} (on={risk_on_votes}, off={risk_off_votes}, "
            f"total={total_votes}, consistency={consistency:.2f})"
        )

        return {
            "time": latest_date,
            "market": "cross_asset",
            "regime": regime,
            "confidence": round(consistency, 6),
            "metadata": {
                "pairs": pair_results,
                "risk_on_votes": risk_on_votes,
                "risk_off_votes": risk_off_votes,
                "total_votes": total_votes,
                "reason_codes": reason_codes,
            },
            "config_version": self.config_version,
        }
