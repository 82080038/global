"""Decision Engine (Fase 4).

Menggabungkan skor dari semua engine menjadi rekomendasi yang dapat dieksekusi.
Menggunakan AI Learning Engine untuk optimasi bobot dinamis berdasarkan regime
dan konsistensi skor historis.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from trading_system.ai_learning.engine import AILearningEngine
from trading_system.config import EXIT_CONVICTION_THRESHOLD, TRADING_CAPITAL
from trading_system.data.storage import DataStorage
from trading_system.risk.engine import RiskEngine
from trading_system.xai.engine import ExplainableAIEngine

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
        self.ai_learning = AILearningEngine(storage)
        self.xai = ExplainableAIEngine(storage)

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

    def _check_fundamental_weight_multiplier(self, ticker: str) -> float:
        """Load weight_multiplier from fundamental engine's stored breakdown.

        Returns 0.0 if fundamental data is unavailable, 0.5 if degraded, 1.0 if ok.
        """
        fund_df = self.storage.load_scores(ticker, engine="fundamental")
        if fund_df.empty:
            return 1.0  # Default: don't penalize if no data in DB
        try:
            import json
            breakdown = json.loads(fund_df.iloc[0]["breakdown"])
            return breakdown.get("_weight_multiplier", 1.0)
        except Exception:
            return 1.0

    def _redistribute_weights(self, weights: dict, ticker: str) -> dict:
        """If fundamental weight_multiplier is 0, redistribute its weight to other factors.

        This ensures that when fundamental data is unavailable (e.g. for .JK stocks),
        the decision engine doesn't use a neutral score but instead ignores
        the fundamental factor entirely and redistributes its weight proportionally.
        """
        wm = self._check_fundamental_weight_multiplier(ticker)

        if wm == 0.0 and "fundamental" in weights and weights["fundamental"] > 0:
            adjusted = weights.copy()
            fund_weight = adjusted.pop("fundamental")
            # Redistribute to technical and macro (most reliable for .JK)
            remaining = sum(adjusted.values())
            if remaining > 0:
                for k in adjusted:
                    adjusted[k] = adjusted[k] + fund_weight * (adjusted[k] / remaining)
            else:
                # Fallback: equal split
                n = len(adjusted) if adjusted else 1
                for k in adjusted:
                    adjusted[k] = fund_weight / n
            return adjusted

        elif wm == 0.5 and "fundamental" in weights:
            # Degraded: halve the fundamental weight, redistribute the other half
            adjusted = weights.copy()
            halved = adjusted["fundamental"] * 0.5
            adjusted["fundamental"] = halved
            remaining = sum(v for k, v in adjusted.items() if k != "fundamental")
            if remaining > 0:
                for k in adjusted:
                    if k != "fundamental":
                        adjusted[k] = adjusted[k] + halved * (adjusted[k] / remaining)
            return adjusted

        return weights

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

    def decide_action(self, conviction: float, risk_flags: list, has_position: bool = False) -> str:
        """State machine sinyal: BUY -> HOLD -> SELL.

        Jika ada posisi terbuka (`has_position=True`) dan konviksi merosot di
        bawah `EXIT_CONVICTION_THRESHOLD`, kembalikan SELL sebagai mekanisme
        exit eksplisit — sebelumnya satu-satunya jalur exit hanya SL/TP/trailing
        stop, sehingga posisi dengan konviksi memburuk tidak pernah dijual
        selama harga belum menyentuh SL (§2.3 SARAN_PENGEMBANGAN.md).
        """
        if has_position and conviction < EXIT_CONVICTION_THRESHOLD:
            return "SELL"
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

    def recommend(self, ticker: str, weights: dict | None = None, capital: float = TRADING_CAPITAL) -> dict[str, Any]:
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

        # Use AI Learning for dynamic weights if no explicit weights provided
        if weights is None:
            weights = self.ai_learning.get_factor_weights(ticker, macro_regime)

        # Redistribute weights if fundamental data is unavailable (weight_multiplier = 0)
        weights = self._redistribute_weights(weights, ticker)

        conviction = self.compute_conviction(adjusted, weights)

        risk = self.risk.analyze(ticker, capital=capital)
        if risk.get("status") == "error":
            return {"status": "error", "message": risk.get("message")}

        has_position = self.storage.get_open_position(ticker) is not None
        action = self.decide_action(conviction, risk.get("risk_flags", []), has_position=has_position)

        last_price = risk.get("last_price")
        if last_price is None or not isinstance(last_price, (int, float)):
            return {"status": "error", "message": "Risk engine did not return a valid last_price."}

        recommendation = {
            "recommendation_id": f"{ticker}_{datetime.now(UTC).isoformat()}",
            "ticker": ticker,
            "action": action,
            "conviction_score": round(conviction, 2),
            "position_size": risk.get("position_size"),
            "entry_price_range": [round(last_price * 0.99, 2), round(last_price * 1.01, 2)],
            "stop_loss": risk.get("stop_loss"),
            "take_profit": risk.get("take_profit"),
            "expected_hold_period": "1-3 months",
            "risk_flags": risk.get("risk_flags", []),
            "contributing_scores": adjusted,
            "weights_used": weights,
            "regime": macro_regime,
            "var_95_1d": risk.get("var_95_1d"),
            "max_drawdown": risk.get("max_drawdown"),
            "created_at": datetime.now(UTC).isoformat(),
        }

        self.storage.audit(
            "decision.recommendation.created",
            recommendation,
        )

        # Send Telegram notification for actionable signals
        if action in ("BUY", "SELL"):
            try:
                from trading_system.utils.notifier import notify_signal
                notify_signal(
                    action=action,
                    ticker=ticker,
                    price=risk["last_price"],
                    conviction=conviction,
                    details={
                        "stop_loss": risk.get("stop_loss"),
                        "take_profit": risk.get("take_profit"),
                        "entry_price_range": recommendation["entry_price_range"],
                        "risk_flags": risk.get("risk_flags", []),
                    },
                )
            except Exception:
                pass  # Don't block recommendation if notifier fails

        # Send risk alert for severe drawdown
        if "SEVERE_DRAWDOWN" in risk.get("risk_flags", []):
            try:
                from trading_system.utils.notifier import notify_risk_alert
                notify_risk_alert(
                    ticker=ticker,
                    alert_type="SEVERE_DRAWDOWN",
                    message=f"Max Drawdown: {risk.get('max_drawdown', 'N/A')}",
                )
            except Exception:
                pass

        # Generate XAI explanation for the recommendation
        explanation = self.xai.explain(ticker, recommendation)
        recommendation["explanation"] = explanation

        return {
            "status": "ok",
            "engine": self.name,
            "recommendation": recommendation,
        }
