"""Score Breakdown & Risk Context Provider untuk XAI.

Memuat breakdown detail dari tabel scores untuk setiap engine dan
menyediakan konteks untuk narasi penjelasan.

Sumber:
- Tabel scores (breakdown JSON per engine per ticker)
- Recommendation dict (risk metrics, regime)
- analysis/manipulation.py (deteksi manipulasi dari OHLCV)
- analysis/red_flags.py (fundamental red flags)
"""

from __future__ import annotations

import json
import logging

from trading_system.data.storage import DataStorage

logger = logging.getLogger("xai.score_context")


class ScoreBreakdownProvider:
    """Load dan interpret breakdown dari setiap engine untuk XAI narrative."""

    def __init__(self, storage: DataStorage | None = None):
        self.storage = storage or DataStorage()

    def _load_breakdowns(self, ticker: str) -> dict[str, dict]:
        """Load breakdown JSON untuk semua engine dari tabel scores."""
        df = self.storage.load_scores(ticker)
        if df.empty:
            return {}
        latest = df.drop_duplicates("engine", keep="first")
        result = {}
        for _, row in latest.iterrows():
            engine = row["engine"]
            try:
                breakdown = json.loads(row["breakdown"]) if row["breakdown"] else {}
            except (json.JSONDecodeError, TypeError):
                breakdown = {}
            result[engine] = {
                "score": float(row["score"]) if row["score"] is not None else None,
                "breakdown": breakdown,
                "as_of": row.get("as_of"),
            }
        return result

    def get_technical_context(self, ticker: str, data: dict) -> dict:
        """Interpret technical breakdown: trend, RSI, MACD, volatility, volume."""
        breakdown = data.get("breakdown", {})
        score = data.get("score")

        trend_score = breakdown.get("trend")
        rsi_score = breakdown.get("rsi")
        macd_score = breakdown.get("macd")
        vol_score = breakdown.get("volatility")
        volume_score = breakdown.get("volume")

        # Infer trend direction from score
        if trend_score is not None:
            if trend_score >= 25:
                trend_dir = "uptrend"
            elif trend_score <= 0:
                trend_dir = "downtrend"
            else:
                trend_dir = "sideways"
        else:
            trend_dir = "unknown"

        # RSI interpretation
        rsi_level = "unknown"
        if rsi_score is not None:
            # rsi_score = (rsi - 30) * (25/40), so rsi = rsi_score * 40/25 + 30
            rsi_raw = rsi_score * 40 / 25 + 30
            if rsi_raw >= 70:
                rsi_level = "overbought"
            elif rsi_raw <= 30:
                rsi_level = "oversold"
            elif rsi_raw >= 55:
                rsi_level = "bullish"
            elif rsi_raw <= 45:
                rsi_level = "bearish"
            else:
                rsi_level = "neutral"

        # MACD interpretation
        macd_signal = "unknown"
        if macd_score is not None:
            macd_signal = "bullish_cross" if macd_score >= 25 else "bearish_cross"

        return {
            "available": bool(breakdown),
            "score": score,
            "trend": trend_dir,
            "trend_score": trend_score,
            "rsi_level": rsi_level,
            "rsi_score": rsi_score,
            "macd_signal": macd_signal,
            "macd_score": macd_score,
            "volatility_score": vol_score,
            "volume_score": volume_score,
        }

    def get_fundamental_context(self, ticker: str, data: dict) -> dict:
        """Interpret fundamental breakdown: PER, PBV, ROE, DER, growth, coverage."""
        breakdown = data.get("breakdown", {})
        score = data.get("score")

        components = {}
        for key in ("PER", "PBV", "ROE", "DER", "growth"):
            if key in breakdown:
                components[key] = breakdown[key]

        coverage = breakdown.get("_data_coverage", 1.0)
        missing = breakdown.get("_missing", [])

        # Interpret valuation
        valuation = "unknown"
        per = components.get("PER")
        pbv = components.get("PBV")
        if per is not None:
            if per < 10:
                valuation = "undervalued"
            elif per > 25:
                valuation = "overvalued"
            else:
                valuation = "fair"

        # Profitability
        roe = components.get("ROE")
        profitability = "unknown"
        if roe is not None:
            if roe >= 20:
                profitability = "excellent"
            elif roe >= 15:
                profitability = "good"
            elif roe >= 10:
                profitability = "average"
            else:
                profitability = "weak"

        # Leverage
        der = components.get("DER")
        leverage = "unknown"
        if der is not None:
            if der < 0.5:
                leverage = "low"
            elif der < 1.0:
                leverage = "moderate"
            else:
                leverage = "high"

        return {
            "available": bool(components),
            "score": score,
            "components": components,
            "valuation": valuation,
            "profitability": profitability,
            "leverage": leverage,
            "data_coverage": coverage,
            "missing": missing,
        }

    def get_macro_context(self, ticker: str, data: dict) -> dict:
        """Interpret macro breakdown: regime, rates."""
        breakdown = data.get("breakdown", {})
        score = data.get("score")
        regime = breakdown.get("regime", "unknown")

        # Macro breakdown stores score components (0-25 each), not actual values.
        # Only extract regime and data_age; skip score components.
        data_age = breakdown.get("data_age_days", {})

        return {
            "available": bool(breakdown),
            "score": score,
            "regime": regime,
            "data_age": data_age,
        }

    def get_global_context(self, ticker: str, data: dict) -> dict:
        """Interpret global market breakdown."""
        breakdown = data.get("breakdown", {})
        score = data.get("score")

        above_50ma = breakdown.get("above_50ma")
        above_200ma = breakdown.get("above_200ma")
        data_age = breakdown.get("data_age_days")

        market_health = "unknown"
        if above_50ma is not None and above_200ma is not None:
            # Values are 0-100 (percentage), not 0-1 decimal
            pct = (above_50ma + above_200ma) / 2
            if pct >= 70:
                market_health = "strong"
            elif pct >= 50:
                market_health = "moderate"
            else:
                market_health = "weak"

        return {
            "available": bool(breakdown),
            "score": score,
            "above_50ma_pct": above_50ma,  # already in 0-100
            "above_200ma_pct": above_200ma,  # already in 0-100
            "market_health": market_health,
            "data_age_days": data_age,
        }

    def get_relationship_context(self, ticker: str, data: dict) -> dict:
        """Interpret relationship breakdown: correlations with global/macro."""
        breakdown = data.get("breakdown", {})
        score = data.get("score")

        # Relationship engine stores correlations in breakdown
        relationships = breakdown.get("relationships", [])
        if not relationships and isinstance(breakdown, dict):
            # Try to extract from breakdown keys
            for key in ("correlations", "assets"):
                if key in breakdown:
                    relationships = breakdown[key]
                    break

        # Find strongest correlation
        strongest = None
        if isinstance(relationships, list):
            for rel in relationships:
                if isinstance(rel, dict) and "correlation" in rel:
                    corr = abs(rel["correlation"])
                    if strongest is None or corr > abs(strongest.get("correlation", 0)):
                        strongest = rel

        return {
            "available": bool(breakdown),
            "score": score,
            "relationships": relationships if isinstance(relationships, list) else [],
            "strongest": strongest,
        }

    def get_sentiment_context(self, ticker: str, data: dict) -> dict:
        """Interpret sentiment breakdown: which sources contributed."""
        breakdown = data.get("breakdown", {})
        score = data.get("score")

        # Sentiment engine stores source scores in breakdown
        sources = {}
        for key in ("foreign_flow", "broker_summary", "social_media", "google_trends", "news_nlp", "idx_historical"):
            if key in breakdown:
                sources[key] = breakdown[key]

        signal = breakdown.get("signal", "unknown")

        return {
            "available": bool(breakdown),
            "score": score,
            "sources": sources,
            "signal": signal,
        }

    def get_risk_context(self, recommendation: dict) -> dict:
        """Extract risk metrics dari recommendation dict."""
        var_95 = recommendation.get("var_95_1d")
        max_dd = recommendation.get("max_drawdown")
        risk_flags = recommendation.get("risk_flags", [])

        # Volatility from risk flags or recommendation
        volatility = None
        for flag in risk_flags:
            if "VOLATILITY" in str(flag).upper():
                volatility = "high"
                break

        return {
            "available": var_95 is not None or max_dd is not None,
            "var_95_1d": var_95,
            "max_drawdown": max_dd,
            "risk_flags": risk_flags,
            "volatility_level": volatility,
        }

    def get_manipulation_context(self, ticker: str) -> dict:
        """Quick manipulation detection dari OHLCV terakhir."""
        try:
            from trading_system.analysis.manipulation import (
                detect_price_volume_divergence,
                detect_volume_anomaly,
            )

            df = self.storage.load_ohlcv(ticker, limit=60)
            if df.empty or len(df) < 20:
                return {"available": False}

            flags = []
            flags.extend(detect_volume_anomaly(df))
            flags.extend(detect_price_volume_divergence(df))

            # Only report recent flags (last 10 bars)
            recent_dates = set(str(d) for d in df.index[-10:])
            recent_flags = [f for f in flags if f.date in recent_dates or str(f.date)[:10] in recent_dates]

            high_severity = [f for f in recent_flags if f.severity == "high"]

            return {
                "available": True,
                "total_flags": len(recent_flags),
                "high_severity_count": len(high_severity),
                "flags": [
                    {"check": f.check, "severity": f.severity, "detail": f.detail}
                    for f in recent_flags[:5]
                ],
                "has_danger": len(high_severity) > 0,
            }
        except Exception as e:
            logger.debug(f"Manipulation check failed for {ticker}: {e}")
            return {"available": False}

    def get_all_contexts(self, ticker: str, recommendation: dict | None = None) -> dict[str, dict]:
        """Load semua context untuk XAI."""
        breakdowns = self._load_breakdowns(ticker)

        contexts: dict[str, dict] = {}

        # Engine-specific contexts
        if "technical" in breakdowns:
            contexts["technical"] = self.get_technical_context(ticker, breakdowns["technical"])
        if "fundamental" in breakdowns:
            contexts["fundamental"] = self.get_fundamental_context(ticker, breakdowns["fundamental"])
        if "macro" in breakdowns:
            contexts["macro"] = self.get_macro_context(ticker, breakdowns["macro"])
        if "global" in breakdowns:
            contexts["global"] = self.get_global_context(ticker, breakdowns["global"])
        if "relationship" in breakdowns:
            contexts["relationship"] = self.get_relationship_context(ticker, breakdowns["relationship"])
        if "sentiment" in breakdowns:
            contexts["sentiment"] = self.get_sentiment_context(ticker, breakdowns["sentiment"])

        # Risk context from recommendation
        if recommendation:
            contexts["risk"] = self.get_risk_context(recommendation)

        # Manipulation check
        contexts["manipulation"] = self.get_manipulation_context(ticker)

        return contexts
