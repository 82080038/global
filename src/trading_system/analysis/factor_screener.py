"""Factor Screener Service (Q, §4.1).

Adapted from TIP/python/engines/screener.py.
Wraps FactorEngine and provides structured output with explanations.
"""

from __future__ import annotations

from typing import Any

from trading_system.analysis.factor_engine import FactorEngine


class FactorScreenerService:
    """Query service for factor-based screening."""

    def __init__(self, engine: FactorEngine):
        self.engine = engine

    def screen(
        self,
        top_n: int = 20,
        min_composite: float = 0.0,
        factor_filter: str | None = None,
        min_factor_rank: float = 0.0,
        tickers: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run factor screen and return top-ranked instruments with breakdown."""
        result = self.engine.compute(tickers=tickers)

        composite = result["composite_ranks"]
        results_list = result["results"]

        instrument_factors: dict[str, dict] = {}
        for r in results_list:
            if r.get("percentile_rank") is not None:
                sym = r.get("symbol", "")
                if sym not in instrument_factors:
                    instrument_factors[sym] = {"factors": {}}
                instrument_factors[sym]["factors"][r["factor_name"]] = {
                    "raw_value": r["raw_value"],
                    "percentile_rank": r["percentile_rank"],
                    "bars_used": r["bars_used"],
                }

        filtered = []
        for symbol, composite_rank in composite.items():
            if composite_rank < min_composite:
                continue
            if factor_filter and symbol in instrument_factors:
                factor_data = instrument_factors[symbol]["factors"].get(factor_filter)
                if factor_data is None or factor_data["percentile_rank"] < min_factor_rank:
                    continue
            filtered.append((symbol, composite_rank))

        filtered.sort(key=lambda x: x[1], reverse=True)
        top = filtered[:top_n]

        screen_results = []
        for symbol, composite_rank in top:
            info = instrument_factors.get(symbol, {"factors": {}})
            screen_results.append({
                "symbol": symbol,
                "composite_rank": composite_rank,
                "factor_breakdown": info["factors"],
            })

        return {
            "as_of": result["as_of"],
            "factor_version": result["factor_version"],
            "universe_size": result["universe_size"],
            "scored_instruments": result["scored_instruments"],
            "screened_count": len(screen_results),
            "results": screen_results,
            "reason_codes": result["reason_codes"],
            "skipped_liquidity": result["skipped_liquidity"],
            "skipped_history": result["skipped_history"],
        }

    def explain(self, symbol: str, tickers: list[str] | None = None) -> dict[str, Any]:
        """Provide explainable factor breakdown for a single instrument."""
        result = self.engine.compute(tickers=tickers)

        instrument_results = [r for r in result["results"] if r.get("symbol") == symbol]
        if not instrument_results:
            return {
                "symbol": symbol,
                "found": False,
                "reason": "Instrument tidak ditemukan dalam hasil faktor",
            }

        composite = result["composite_ranks"]
        composite_rank = composite.get(symbol)

        explanations = []
        for r in instrument_results:
            if r.get("percentile_rank") is not None:
                rank_pct = r["percentile_rank"] * 100
                if rank_pct >= 80:
                    tier = "top quintile"
                elif rank_pct >= 60:
                    tier = "above average"
                elif rank_pct >= 40:
                    tier = "average"
                elif rank_pct >= 20:
                    tier = "below average"
                else:
                    tier = "bottom quintile"
                explanations.append({
                    "factor": r["factor_name"],
                    "raw_value": r["raw_value"],
                    "percentile_rank": r["percentile_rank"],
                    "tier": tier,
                    "bars_used": r["bars_used"],
                    "explanation": f"Faktor {r['factor_name']} berada di {tier} (persentil {rank_pct:.1f}%)",
                })

        return {
            "symbol": symbol,
            "found": True,
            "composite_rank": composite_rank,
            "factor_version": result["factor_version"],
            "as_of": result["as_of"],
            "factors": explanations,
        }
