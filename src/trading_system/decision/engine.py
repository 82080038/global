"""Decision Engine (Fase 4).

Menggabungkan skor dari semua engine menjadi rekomendasi yang dapat dieksekusi.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from trading_system.data.storage import DataStorage
from trading_system.risk.engine import RiskEngine


DEFAULT_WEIGHTS = {
    "technical": 0.20,
    "fundamental": 0.25,
    "macro": 0.15,
    "global": 0.15,
    "relationship": 0.10,
    "sentiment": 0.15,
}


class DecisionEngine:
    name = "decision"

    def __init__(self, storage: DataStorage | None = None):
        self.storage = storage or DataStorage()
        self.risk = RiskEngine(storage)

    def load_latest_scores(self, ticker: str) -> dict:
        df = self.storage.load_scores(ticker)
        if df.empty:
            return {}
        latest = df.drop_duplicates("engine").set_index("engine")
        return {idx: float(row["score"]) for idx, row in latest.iterrows()}

    def apply_regime_filter(self, scores: dict, macro_regime: str | None) -> dict:
        # Adjust technical/macro/global scores based on regime
        adjusted = scores.copy()
        if macro_regime == "tightening":
            adjusted["macro"] = adjusted.get("macro", 50) * 0.8
            adjusted["technical"] = adjusted.get("technical", 50) * 0.9
        elif macro_regime == "easing":
            adjusted["macro"] = min(100, adjusted.get("macro", 50) * 1.1)
            adjusted["fundamental"] = min(100, adjusted.get("fundamental", 50) * 1.05)
        return adjusted

    def compute_conviction(self, scores: dict, weights: dict | None = None) -> float:
        w = weights or DEFAULT_WEIGHTS
        total = 0.0
        weight_sum = 0.0
        for k, weight in w.items():
            if k in scores and scores[k] is not None:
                total += scores[k] * weight
                weight_sum += weight
        if weight_sum == 0:
            return 0.0
        return total / weight_sum

    def decide_action(self, conviction: float, risk_flags: list) -> str:
        if "HIGH_VOLATILITY" in risk_flags or "LIQUIDITY_LOW" in risk_flags:
            if conviction < 60:
                return "AVOID"
        if conviction >= 70:
            return "BUY"
        if conviction >= 55:
            return "WATCHLIST"
        if conviction >= 40:
            return "HOLD"
        return "AVOID"

    def recommend(self, ticker: str, weights: dict | None = None) -> dict[str, Any]:
        scores = self.load_latest_scores(ticker)
        if not scores:
            return {"status": "error", "message": f"No scores available for {ticker}. Run compute-scores first."}

        # Try to load macro regime from scores breakdown
        macro_regime = None
        macro_df = self.storage.load_scores(ticker, engine="macro")
        if not macro_df.empty:
            try:
                import json
                breakdown = json.loads(macro_df.iloc[0]["breakdown"])
                macro_regime = breakdown.get("regime")
            except Exception:
                pass

        adjusted = self.apply_regime_filter(scores, macro_regime)
        conviction = self.compute_conviction(adjusted, weights)

        risk = self.risk.analyze(ticker)
        if risk.get("status") == "error":
            return {"status": "error", "message": risk.get("message")}

        action = self.decide_action(conviction, risk.get("risk_flags", []))

        recommendation = {
            "recommendation_id": f"{ticker}_{datetime.now(timezone.utc).isoformat()}",
            "ticker": ticker,
            "action": action,
            "conviction_score": round(conviction, 2),
            "position_size": risk.get("position_size"),
            "entry_price_range": [round(risk["last_price"] * 0.99, 2), round(risk["last_price"] * 1.01, 2)],
            "stop_loss": risk.get("stop_loss"),
            "take_profit": risk.get("take_profit"),
            "expected_hold_period": "1-3 months",
            "risk_flags": risk.get("risk_flags", []),
            "contributing_scores": adjusted,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        self.storage.audit(
            "decision.recommendation.created",
            recommendation,
        )

        return {
            "status": "ok",
            "engine": self.name,
            "recommendation": recommendation,
        }
