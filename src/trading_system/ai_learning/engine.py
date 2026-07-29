"""AI Learning Engine (Fase 5) — placeholder.

Saat ini mengembalikan default factor weights dan statistik sederhana
karena data forward return belum cukup untuk retraining.
"""

from __future__ import annotations

from trading_system.data.storage import DataStorage
from trading_system.decision.engine import DEFAULT_WEIGHTS


class AILearningEngine:
    name = "ai_learning"

    def __init__(self, storage: DataStorage | None = None):
        self.storage = storage or DataStorage()

    def get_factor_weights(self, ticker: str | None = None, regime: str | None = None) -> dict:
        # Placeholder: return default weights, nanti dapat di-update dari histori
        return DEFAULT_WEIGHTS.copy()

    def feature_importance(self, scores: dict) -> list[dict]:
        total = sum(s for s in scores.values() if s is not None)
        if total == 0:
            return []
        return [
            {"factor": k, "importance": round(v / total, 4) if v is not None else 0}
            for k, v in scores.items()
        ]
