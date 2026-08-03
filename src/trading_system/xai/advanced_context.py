"""Advanced Analysis Context Provider untuk XAI.

Menyediakan konteks dari engine-engine lanjutan yang sebelumnya belum
terintegrasi ke ExplainableAIEngine:

- EnhancedRegimeEngine: regime pasar global (risk_on/risk_off/neutral)
- CrossAssetEngine: cross-asset beta, correlation, risk-on/off consistency
- PatternReliabilityEngine: historical pattern win-rate
- NoTradeEngine: gate-based trade filter
- FactorEngine: cross-sectional factor ranking (momentum, volatility, quality, beta, size, value)

Semua engine bersifat "best-effort" — jika data tidak tersedia atau
engine gagal, context mengembalikan available=False dan XAI melanjutkan
tanpa bagian tersebut.
"""

from __future__ import annotations

import logging

from trading_system.data.storage import DataStorage

logger = logging.getLogger("xai.advanced_context")


class AdvancedAnalysisProvider:
    """Provider untuk engine-engine analisis lanjutan."""

    def __init__(self, storage: DataStorage | None = None):
        self.storage = storage or DataStorage()

    # ---------- Enhanced Regime ----------

    def get_enhanced_regime_context(self) -> dict:
        """Jalankan EnhancedRegimeEngine untuk dapatkan regime global."""
        try:
            from trading_system.analysis.enhanced_regime import EnhancedRegimeEngine

            engine = EnhancedRegimeEngine(self.storage)
            result = engine.compute()

            regime = result.get("regime", "unknown")
            confidence = result.get("confidence", 0.0)
            metadata = result.get("metadata", {})
            score = metadata.get("score", 0.0)
            components = metadata.get("components", [])
            skipped = metadata.get("skipped", [])

            # Top contributing components
            top_components = sorted(components, key=lambda c: abs(c.get("z", 0)), reverse=True)[:3]

            return {
                "available": regime != "unknown",
                "regime": regime,
                "confidence": round(confidence, 4),
                "score": round(score, 4),
                "top_components": [
                    {"key": c.get("key"), "z": c.get("z"), "return": c.get("latest_return")}
                    for c in top_components
                ],
                "skipped": skipped,
            }
        except Exception as e:
            logger.debug(f"EnhancedRegime failed: {e}")
            return {"available": False}

    # ---------- Cross-Asset ----------

    def get_cross_asset_context(self) -> dict:
        """Jalankan CrossAssetEngine untuk cross-asset beta & regime."""
        try:
            from trading_system.analysis.cross_asset import CrossAssetEngine

            engine = CrossAssetEngine(self.storage)
            result = engine.compute()

            regime = result.get("regime", "unknown")
            confidence = result.get("confidence", 0.0)
            metadata = result.get("metadata", {})
            pairs = metadata.get("pairs", [])
            risk_on = metadata.get("risk_on_votes", 0)
            risk_off = metadata.get("risk_off_votes", 0)

            # Find strongest correlations
            strongest = sorted(pairs, key=lambda p: abs(p.get("correlation", 0)), reverse=True)[:3]

            return {
                "available": regime != "unknown" and len(pairs) > 0,
                "regime": regime,
                "confidence": round(confidence, 4),
                "risk_on_votes": risk_on,
                "risk_off_votes": risk_off,
                "strongest_pairs": [
                    {
                        "label": p.get("label"),
                        "correlation": p.get("correlation"),
                        "beta": p.get("beta"),
                        "target_z": p.get("target_z"),
                    }
                    for p in strongest
                ],
                "total_pairs": len(pairs),
            }
        except Exception as e:
            logger.debug(f"CrossAsset failed: {e}")
            return {"available": False}

    # ---------- Pattern Reliability ----------

    def get_pattern_reliability_context(self, ticker: str) -> dict:
        """Cek pattern reliability untuk ticker dari ExtendedStorage."""
        try:
            from trading_system.analysis.pattern_reliability import PatternReliabilityEngine

            engine = PatternReliabilityEngine()
            kode = ticker.replace(".JK", "")

            # Get reliable patterns for this stock
            df = engine.get_reliable_patterns(kode=kode, min_win_rate=50.0, min_rating="average")
            if df.empty:
                return {"available": True, "patterns": [], "top_patterns": []}

            # Top patterns by win_rate
            top = df.head(5)
            top_patterns = []
            for _, row in top.iterrows():
                top_patterns.append({
                    "pattern": row.get("pattern", ""),
                    "win_rate": float(row.get("win_rate", 0)),
                    "total_occurrences": int(row.get("total_occurrences", 0)),
                    "avg_return_5d": float(row.get("avg_return_5d", 0)),
                    "avg_return_10d": float(row.get("avg_return_10d", 0)),
                    "rating": row.get("reliability_rating", "average"),
                })

            return {
                "available": True,
                "patterns": len(df),
                "top_patterns": top_patterns,
            }
        except Exception as e:
            logger.debug(f"PatternReliability failed for {ticker}: {e}")
            return {"available": False}

    # ---------- No-Trade Gate ----------

    def get_no_trade_context(
        self,
        ticker: str,
        conviction: float,
        regime_state: str = "neutral",
    ) -> dict:
        """Evaluasi No-Trade gates untuk ticker."""
        try:
            from trading_system.analysis.no_trade import NoTradeConfig, NoTradeEngine

            engine = NoTradeEngine(NoTradeConfig())

            # Gather inputs from storage
            df = self.storage.load_ohlcv(ticker, limit=100)
            liquidity_volume = int(df["volume"].mean()) if not df.empty and "volume" in df.columns else 0
            bars_history = len(df) if not df.empty else 0

            # Latest data date
            latest_data_date = None
            if not df.empty:
                import pandas as pd
                latest_data_date = pd.to_datetime(df.index[-1]).to_pydatetime()

            # Alpha signal from conviction
            alpha_signal = {
                "confidence": conviction / 100.0,
                "composite_alpha": conviction / 100.0,
            }

            result = engine.evaluate(
                alpha_signal=alpha_signal,
                regime_state=regime_state,
                liquidity_volume=liquidity_volume,
                bars_history=bars_history,
                latest_data_date=latest_data_date,
            )

            return {
                "available": True,
                "decision": result.decision,
                "gates_failed": result.gates_failed,
                "gates_passed": result.gates_passed,
                "reason_codes": result.reason_codes,
                "liquidity_volume": liquidity_volume,
                "bars_history": bars_history,
            }
        except Exception as e:
            logger.debug(f"NoTrade failed for {ticker}: {e}")
            return {"available": False}

    # ---------- Factor Engine ----------

    def get_factor_context(self, ticker: str) -> dict:
        """Get cross-sectional factor ranking untuk ticker."""
        try:
            from trading_system.analysis.factor_engine import FactorEngine

            engine = FactorEngine(self.storage)
            result = engine.compute()

            # Find this ticker in results
            symbol = ticker.replace(".JK", "")
            ticker_results = [r for r in result.get("results", []) if r.get("symbol", "").replace(".JK", "") == symbol]

            if not ticker_results:
                return {"available": False, "reason": "ticker not in factor universe"}

            # Build factor summary
            factors = []
            for r in ticker_results:
                factors.append({
                    "factor": r.get("factor_name", ""),
                    "raw_value": r.get("raw_value"),
                    "percentile_rank": r.get("percentile_rank"),
                    "bars_used": r.get("bars_used", 0),
                })

            # Sort by percentile rank
            factors.sort(key=lambda f: f.get("percentile_rank") or 0.5, reverse=True)

            composite_rank = result.get("composite_ranks", {}).get(symbol)

            return {
                "available": True,
                "composite_rank": composite_rank,
                "factors": factors[:6],
                "factor_version": result.get("factor_version", "1.0"),
                "universe_size": result.get("universe_size", 0),
            }
        except Exception as e:
            logger.debug(f"FactorEngine failed for {ticker}: {e}")
            return {"available": False}

    # ---------- Combined ----------

    def get_all_contexts(
        self,
        ticker: str,
        conviction: float = 50.0,
        regime_state: str = "neutral",
    ) -> dict:
        """Load semua advanced context untuk XAI."""
        return {
            "enhanced_regime": self.get_enhanced_regime_context(),
            "cross_asset": self.get_cross_asset_context(),
            "pattern_reliability": self.get_pattern_reliability_context(ticker),
            "no_trade": self.get_no_trade_context(ticker, conviction, regime_state),
            "factor": self.get_factor_context(ticker),
        }
