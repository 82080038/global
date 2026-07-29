"""Score Pipeline / Analysis Layer Orchestrator (Fase 2)."""

from __future__ import annotations

from datetime import datetime, timezone

from trading_system.analysis.technical import TechnicalAnalysisEngine
from trading_system.analysis.fundamental import FundamentalAnalysisEngine
from trading_system.analysis.macro import MacroEconomicEngine
from trading_system.analysis.global_market import GlobalMarketEngine
from trading_system.intelligence.relationship import MarketRelationshipEngine
from trading_system.corporate.actions import CorporateActionEngine
from trading_system.sentiment.engine import SentimentEngine
from trading_system.data.storage import DataStorage
from trading_system.data.acquisition import YahooFinanceAdapter, normalize_ohlcv
from trading_system.data.validation import DataQualityValidator


class AnalysisPipeline:
    def __init__(self, storage: DataStorage | None = None):
        self.storage = storage or DataStorage()
        self.technical = TechnicalAnalysisEngine()
        self.fundamental = FundamentalAnalysisEngine()
        self.macro = MacroEconomicEngine(self.storage)
        self.global_market = GlobalMarketEngine(self.storage)
        self.relationship = MarketRelationshipEngine(self.storage)
        self.corporate = CorporateActionEngine(self.storage)
        self.sentiment = SentimentEngine(self.storage)

    def ensure_ohlcv(self, ticker: str, period: str = "2y") -> bool:
        df = self.storage.load_ohlcv(ticker)
        if not df.empty:
            return True
        adapter = YahooFinanceAdapter()
        result = adapter.fetch(ticker, period=period)
        if result["status"] == "ok":
            validator = DataQualityValidator()
            raw = normalize_ohlcv(result["records"])
            clean, _ = validator.validate(raw)
            self.storage.save_ohlcv(clean)
            return True
        return False

    def compute(self, ticker: str, period: str = "2y") -> dict:
        if not self.ensure_ohlcv(ticker, period):
            return {"status": "error", "message": f"Unable to load OHLCV for {ticker}"}

        # Technical
        self.technical.load_ohlcv(self.storage, ticker)
        tech = self.technical.analyze()

        # Fundamental
        self.fundamental.fetch(ticker)
        fund = self.fundamental.analyze()

        # Macro
        macro = self.macro.analyze(period)

        # Global
        glob = self.global_market.analyze(period)

        # Relationship
        rel = self.relationship.compute(ticker)

        # Corporate actions
        corp = self.corporate.fetch(ticker)

        # Sentiment
        sent = self.sentiment.compute(ticker)

        results = {
            "technical": tech,
            "fundamental": fund,
            "macro": macro,
            "global": glob,
            "relationship": rel,
            "sentiment": sent,
        }

        as_of = datetime.now(timezone.utc).isoformat()
        for engine, res in results.items():
            if res.get("status") in ("ok", "warning") and res.get("score") is not None:
                self.storage.save_score(
                    ticker,
                    engine,
                    res["score"],
                    res.get("breakdown", {}),
                    as_of=as_of,
                )

        return {
            "status": "ok",
            "ticker": ticker,
            "as_of": as_of,
            "scores": {
                k: v.get("score") if isinstance(v, dict) else None
                for k, v in results.items()
            },
            "details": results,
        }
