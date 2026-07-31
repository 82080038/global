"""Enhanced Regime Detector (F, §4.1).

Adapted from TIP/python/engines/global_regime.py and indonesia_regime.py.
Uses SQLite DataStorage instead of PostgreSQL.

Classifies regime as risk_on / risk_off / neutral using z-scores of
daily returns for key global indices, FX and rates.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np

from trading_system.data.storage import DataStorage

CONFIG_VERSION = "2.0"

DEFAULT_CONFIG = [
    {"key": "sp500", "symbol": "^GSPC", "weight": 0.25, "direction": 1},
    {"key": "nasdaq", "symbol": "^IXIC", "weight": 0.20, "direction": 1},
    {"key": "nikkei", "symbol": "^N225", "weight": 0.15, "direction": 1},
    {"key": "hangseng", "symbol": "^HSI", "weight": 0.15, "direction": 1},
    {"key": "dxy", "symbol": "DX-Y.NYB", "weight": 0.15, "direction": -1},
    {"key": "usdidr", "symbol": "USDIDR=X", "weight": 0.10, "direction": -1},
]

LOOKBACK = 60
MIN_COVERAGE = 20
MAX_STALE_DAYS = 7


class EnhancedRegimeEngine:
    """Classify global risk regime as risk_on / risk_off / neutral using
    rank-based z-scores of daily returns for key global indices, FX and rates.

    Adapted from TIP GlobalRegimeEngine — uses SQLite DataStorage.
    """

    DEFAULT_CONFIG = DEFAULT_CONFIG
    LOOKBACK = LOOKBACK

    def __init__(
        self,
        storage: DataStorage | None = None,
        config: list[dict[str, Any]] | None = None,
        config_version: str = CONFIG_VERSION,
        as_of: datetime | None = None,
    ):
        self.storage = storage or DataStorage()
        self.config = config or self.DEFAULT_CONFIG
        self.config_version = config_version
        self.as_of = as_of or datetime.now(UTC)

    def _load_returns(self, symbol: str) -> tuple[list, np.ndarray, np.ndarray] | None:
        """Load returns from SQLite DataStorage."""
        df = self.storage.load_ohlcv(symbol)
        if df is None or df.empty or len(df) < 3:
            return None
        df = df.sort_index()
        closes = df["close"].values.astype(float)
        if len(closes) < 3:
            return None
        returns = np.diff(closes) / closes[:-1]
        times = list(df.index)
        return times, closes, returns

    def _check_stale(self, latest_time) -> tuple[bool, str]:
        if isinstance(latest_time, datetime):
            if latest_time.tzinfo is None:
                latest_time = latest_time.replace(tzinfo=UTC)
            age = (self.as_of - latest_time).days
            if age > MAX_STALE_DAYS:
                return True, f"Data terakhir {age} hari lalu (stale > {MAX_STALE_DAYS} hari)"
        return False, ""

    def compute(self) -> dict[str, Any]:
        """Compute regime classification.

        Returns dict with: time, market, regime, confidence, metadata, config_version, feature_snapshot.
        """
        weighted_score = 0.0
        total_weight = 0.0
        latest_date = None
        components = []
        reason_codes: list[str] = []
        feature_snapshot: dict[str, Any] = {}
        skipped = []

        for cfg in self.config:
            symbol = cfg.get("symbol", cfg.get("key", ""))
            data = self._load_returns(symbol)
            if data is None:
                skipped.append(cfg["key"])
                reason_codes.append(f"COVERAGE_FAIL:{cfg['key']} (data < 3 bar)")
                continue

            times, closes, returns = data
            if len(returns) < 1:
                skipped.append(cfg["key"])
                reason_codes.append(f"COVERAGE_FAIL:{cfg['key']} (returns < 1)")
                continue

            min_cov = MIN_COVERAGE
            if len(returns) < min_cov:
                skipped.append(cfg["key"])
                reason_codes.append(f"COVERAGE_FAIL:{cfg['key']} (returns {len(returns)} < {min_cov})")
                continue

            is_stale, stale_reason = self._check_stale(times[-1])
            if is_stale:
                skipped.append(cfg["key"])
                reason_codes.append(f"STALE_DATA:{cfg['key']} ({stale_reason})")
                continue

            historical = returns[:-1] if len(returns) > 1 else returns
            latest = returns[-1]
            mean = float(np.mean(historical))
            std = float(np.std(historical, ddof=1)) if len(historical) > 1 else 0.0
            z = 0.0 if std < 1e-12 else (latest - mean) / std
            z = z * cfg["direction"]

            weighted_score += z * cfg["weight"]
            total_weight += cfg["weight"]
            latest_date = times[-1]
            components.append({
                "symbol": symbol,
                "key": cfg["key"],
                "z": round(float(z), 4),
                "latest_return": round(float(latest), 6),
                "weight": cfg["weight"],
            })
            feature_snapshot[cfg["key"]] = {
                "z": round(float(z), 4),
                "latest_return": round(float(latest), 6),
                "bars": len(returns),
            }

        if total_weight == 0:
            return {
                "time": latest_date,
                "market": "global",
                "regime": "unknown",
                "confidence": 0.0,
                "metadata": {
                    "score": 0.0,
                    "components": components,
                    "reason_codes": reason_codes,
                    "skipped": skipped,
                },
                "config_version": self.config_version,
                "feature_snapshot": feature_snapshot,
            }

        config_weight = sum(c["weight"] for c in self.config)
        if total_weight < config_weight * 0.5:
            reason_codes.append(
                f"INSUFFICIENT_COVERAGE: only {total_weight:.2f}/{config_weight:.2f} weight available"
            )
            return {
                "time": latest_date,
                "market": "global",
                "regime": "unknown",
                "confidence": 0.0,
                "metadata": {
                    "score": 0.0,
                    "components": components,
                    "reason_codes": reason_codes,
                    "skipped": skipped,
                },
                "config_version": self.config_version,
                "feature_snapshot": feature_snapshot,
            }

        score = float(weighted_score / total_weight)
        if score > 0.5:
            regime = "risk_on"
            reason_codes.append(f"REGIME_RISK_ON: score {score:.4f} > 0.5")
        elif score < -0.5:
            regime = "risk_off"
            reason_codes.append(f"REGIME_RISK_OFF: score {score:.4f} < -0.5")
        else:
            regime = "neutral"
            reason_codes.append(f"REGIME_NEUTRAL: score {score:.4f} in [-0.5, 0.5]")

        return {
            "time": latest_date,
            "market": "global",
            "regime": regime,
            "confidence": round(min(abs(score), 1.0), 6),
            "metadata": {
                "score": round(score, 4),
                "components": components,
                "reason_codes": reason_codes,
                "skipped": skipped,
            },
            "config_version": self.config_version,
            "feature_snapshot": feature_snapshot,
        }
