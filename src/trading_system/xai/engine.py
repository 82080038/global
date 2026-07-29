"""Explainable AI Engine (Fase 5).

Menghasilkan narasi penjelasan untuk setiap rekomendasi.
"""

from __future__ import annotations

from trading_system.data.storage import DataStorage


class ExplainableAIEngine:
    name = "xai"

    def __init__(self, storage: DataStorage | None = None):
        self.storage = storage or DataStorage()

    def explain(self, ticker: str, recommendation: dict | None = None) -> dict:
        if recommendation is None:
            return {"status": "error", "message": "recommendation dict required"}

        action = recommendation.get("action")
        conviction = recommendation.get("conviction_score", 0)
        scores = recommendation.get("contributing_scores", {})
        risk_flags = recommendation.get("risk_flags", [])

        # Faktor paling memengaruhi
        sorted_scores = sorted(scores.items(), key=lambda x: x[1] or 0, reverse=True)
        top_factor = sorted_scores[0][0] if sorted_scores else "unknown"
        bottom_factor = sorted_scores[-1][0] if sorted_scores else "unknown"

        # Confidence interval sederhana
        confidence_low = max(0, conviction - 10)
        confidence_high = min(100, conviction + 10)

        # Counter-scenario sederhana
        scenarios = [
            "Jika USD/IDR melemah 5%, fundamental score bisa turun dan stop loss perlu diperketat.",
            "Jika IHSG tumbuh 2% dalam seminggu, conviction bisa naik ke level BUY.",
        ]

        explanation = {
            "status": "ok",
            "ticker": ticker,
            "action": action,
            "narrative": (
                f"Rekomendasi {action} untuk {ticker} dibentuk dengan conviction {conviction:.1f}. "
                f"Faktor paling mendukung adalah {top_factor} (score: {scores.get(top_factor)}). "
                f"Faktor paling menahan adalah {bottom_factor} (score: {scores.get(bottom_factor)}). "
            ),
            "top_factors": sorted_scores[:3],
            "confidence_interval": [round(confidence_low, 2), round(confidence_high, 2)],
            "risk_summary": risk_flags if risk_flags else ["No critical risk flags"],
            "counter_scenarios": scenarios,
        }
        return explanation
