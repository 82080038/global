"""Pattern Reliability Engine — integrates pattern_reliability & pattern_candidates tables.

Uses historical pattern win-rate data (imported from MySQL data_pasar_modal) to
score and filter detected chart patterns by their historical reliability.

Integrates with:
  - analysis/technical.py (pattern detection)
  - analysis/screener.py (screener filtering)
  - decision/engine.py (decision scoring)
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from trading_system.data.extended_storage import ExtendedStorage

logger = logging.getLogger(__name__)


class PatternReliabilityEngine:
    """Score patterns by historical reliability data."""

    def __init__(self) -> None:
        self.ext = ExtendedStorage()

    def get_reliable_patterns(
        self, kode: str | None = None, min_win_rate: float = 60.0, min_rating: str = "average"
    ) -> pd.DataFrame:
        """Get patterns that meet reliability criteria."""
        df = self.ext.get_pattern_reliability(kode=kode, min_rating=min_rating)
        if df.empty:
            return df
        return df[df["win_rate"] >= min_win_rate].sort_values("win_rate", ascending=False)

    def score_pattern(self, kode: str, pattern_name: str) -> dict[str, Any]:
        """Get reliability score for a specific pattern on a stock.

        Returns dict with win_rate, reliability_rating, avg_returns, etc.
        """
        df = self.ext.get_pattern_reliability(kode=kode)
        if df.empty:
            return {"found": False, "win_rate": None, "rating": None}

        match = df[df["pattern"].str.lower() == pattern_name.lower()]
        if match.empty:
            return {"found": False, "win_rate": None, "rating": None}

        row = match.iloc[0]
        return {
            "found": True,
            "pattern": row["pattern"],
            "pattern_type": row.get("pattern_type"),
            "win_rate": float(row.get("win_rate", 0)),
            "total_occurrences": int(row.get("total_occurrences", 0)),
            "success_count": int(row.get("success_count", 0)),
            "fail_count": int(row.get("fail_count", 0)),
            "avg_return_5d": float(row.get("avg_return_5d", 0)),
            "avg_return_10d": float(row.get("avg_return_10d", 0)),
            "avg_return_20d": float(row.get("avg_return_20d", 0)),
            "reliability_rating": row.get("reliability_rating", "average"),
            "last_detected": row.get("last_detected"),
            "last_outcome": row.get("last_outcome"),
        }

    def get_top_candidates(self, kode: str | None = None, limit: int = 20) -> pd.DataFrame:
        """Get top pattern candidates by preliminary score."""
        return self.ext.get_pattern_candidates(kode=kode, status="candidate").head(limit)

    def get_advanced_features_score(self, kode: str) -> dict:
        """Get advanced features (order flow, volume profile, anomalies) for a stock."""
        return self.ext.get_advanced_features_parsed(kode)

    def enrich_technical_signals(
        self, ticker: str, detected_patterns: list[str]
    ) -> list[dict[str, Any]]:
        """Enrich detected technical patterns with reliability data.

        Args:
            ticker: Stock ticker (e.g. 'BBCA.JK').
            detected_patterns: List of pattern names detected by technical engine.

        Returns:
            List of dicts with pattern name, reliability score, and recommendation.
        """
        kode = ticker.replace(".JK", "")
        results = []
        for pattern in detected_patterns:
            reliability = self.score_pattern(kode, pattern)
            results.append({
                "pattern": pattern,
                "reliable": reliability.get("found", False),
                "win_rate": reliability.get("win_rate"),
                "rating": reliability.get("reliability_rating"),
                "avg_return_5d": reliability.get("avg_return_5d"),
                "avg_return_10d": reliability.get("avg_return_10d"),
                "avg_return_20d": reliability.get("avg_return_20d"),
                "recommendation": self._pattern_recommendation(reliability),
            })
        return results

    def _pattern_recommendation(self, reliability: dict) -> str:
        """Generate recommendation based on pattern reliability."""
        if not reliability.get("found"):
            return "unverified"
        win_rate = reliability.get("win_rate", 0)
        rating = reliability.get("reliability_rating", "average")
        if win_rate >= 80 and rating in ("excellent", "good"):
            return "strong_buy"
        elif win_rate >= 60:
            return "buy"
        elif win_rate >= 40:
            return "hold"
        else:
            return "avoid"
