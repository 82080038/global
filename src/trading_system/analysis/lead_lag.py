"""Lead-Lag Analyzer (BB, §4.1).

Raw copy from TIP/python/engines/lead_lag.py.
Identifies leading and lagging instruments based on cross-correlation
at various offsets. Research/diagnostic tool, not a trading signal.
"""

from __future__ import annotations

from typing import Any

import numpy as np

MAX_OFFSET = 10
MIN_BARS = 30
CORR_THRESHOLD = 0.3


class LeadLagAnalyzer:
    """Analyze lead-lag relationships using cross-correlation at various day offsets."""

    def __init__(
        self,
        max_offset: int = MAX_OFFSET,
        min_bars: int = MIN_BARS,
        corr_threshold: float = CORR_THRESHOLD,
    ):
        self.max_offset = max_offset
        self.min_bars = min_bars
        self.corr_threshold = corr_threshold

    def _cross_correlate(
        self,
        leader: np.ndarray,
        follower: np.ndarray,
        offset: int,
    ) -> float:
        if offset == 0:
            min_len = min(len(leader), len(follower))
            if min_len < 5:
                return 0.0
            l = leader[-min_len:]
            f = follower[-min_len:]
        elif offset > 0:
            min_len = min(len(leader) - offset, len(follower) - offset)
            if min_len < 5:
                return 0.0
            l = leader[-(min_len + offset):-offset]
            f = follower[-min_len:]
        else:
            offset = abs(offset)
            min_len = min(len(leader) - offset, len(follower) - offset)
            if min_len < 5:
                return 0.0
            l = leader[-min_len:]
            f = follower[-(min_len + offset):-offset]

        # Filter NaN values
        valid = ~(np.isnan(l) | np.isnan(f))
        if valid.sum() < 5:
            return 0.0
        l = l[valid]
        f = f[valid]
        if np.std(l) < 1e-12 or np.std(f) < 1e-12:
            return 0.0
        return float(np.corrcoef(l, f)[0, 1])

    def analyze_pair(
        self,
        leader_returns: np.ndarray,
        follower_returns: np.ndarray,
        leader_label: str = "leader",
        follower_label: str = "follower",
    ) -> dict[str, Any]:
        if len(leader_returns) < self.min_bars or len(follower_returns) < self.min_bars:
            return {
                "leader": leader_label,
                "follower": follower_label,
                "best_offset": 0,
                "best_corr": 0.0,
                "significant": False,
                "direction": "none",
                "note": "Data terlalu pendek",
            }

        results = {}
        for offset in range(-self.max_offset, self.max_offset + 1):
            corr = self._cross_correlate(leader_returns, follower_returns, offset)
            results[offset] = corr

        best_offset = max(results, key=lambda k: abs(results[k]))
        best_corr = results[best_offset]

        if abs(best_corr) < self.corr_threshold:
            direction = "none"
            significant = False
        elif best_offset > 0:
            direction = "leader_leads"
            significant = True
        elif best_offset < 0:
            direction = "follower_leads"
            significant = True
        else:
            direction = "synchronous"
            significant = abs(best_corr) >= self.corr_threshold

        return {
            "leader": leader_label,
            "follower": follower_label,
            "best_offset": best_offset,
            "best_corr": round(best_corr, 4),
            "significant": significant,
            "direction": direction,
            "all_corrs": {str(k): round(v, 4) for k, v in sorted(results.items())},
        }

    def analyze_multiple(
        self,
        returns_data: dict[str, np.ndarray],
        pairs: list[tuple[str, str]],
    ) -> list[dict[str, Any]]:
        results = []
        for leader_label, follower_label in pairs:
            if leader_label not in returns_data or follower_label not in returns_data:
                results.append({
                    "leader": leader_label,
                    "follower": follower_label,
                    "best_offset": 0,
                    "best_corr": 0.0,
                    "significant": False,
                    "direction": "none",
                    "note": "Data tidak tersedia",
                })
                continue
            result = self.analyze_pair(
                returns_data[leader_label],
                returns_data[follower_label],
                leader_label,
                follower_label,
            )
            results.append(result)
        return results
