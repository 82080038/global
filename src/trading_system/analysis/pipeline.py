"""Score Pipeline / Analysis Layer Orchestrator (Fase 2)."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from trading_system.analysis.fundamental import FundamentalAnalysisEngine
from trading_system.analysis.global_market import GlobalMarketEngine
from trading_system.analysis.macro import MacroEconomicEngine
from trading_system.analysis.relationship import MarketRelationshipEngine
from trading_system.analysis.technical import TechnicalAnalysisEngine
from trading_system.corporate.actions import CorporateActionEngine
from trading_system.data.acquisition import YahooFinanceAdapter, normalize_ohlcv
from trading_system.data.archive import ArchiveAdapter
from trading_system.data.storage import DataStorage
from trading_system.data.validation import DataQualityValidator
from trading_system.sentiment.engine import SentimentEngine


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
        self.archive = ArchiveAdapter()

    def ensure_ohlcv(self, ticker: str, period: str = "2y") -> bool:
        df = self.storage.load_ohlcv(ticker)
        if not df.empty:
            # Incremental fetch: only get data newer than last timestamp (§4.1)
            last_ts = str(df.index[-1])[:10]
            # Cek apakah data sudah cukup baru (hari ini atau kemarin)
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            if last_ts >= today:
                return True  # Data sudah mutakhir, tidak perlu fetch
            # Coba Parquet archive dulu sebelum Yahoo Finance
            arch_df = self.archive.load_ohlcv(ticker, start=last_ts)
            if not arch_df.empty:
                last_ts_pd = pd.Timestamp(last_ts)
                if arch_df.index.tz is not None:
                    last_ts_pd = last_ts_pd.tz_localize(arch_df.index.tz)
                new_df = arch_df[arch_df.index > last_ts_pd]
                if not new_df.empty:
                    new_df = new_df.reset_index()
                    new_df["ticker"] = ticker
                    new_df["asset_class"] = "equity"
                    new_df["exchange"] = "INDO" if ticker.endswith(".JK") else "GLOBAL"
                    new_df["timeframe"] = "1d"
                    new_df["source"] = "archive"
                    new_df["ingested_at"] = datetime.now(UTC).isoformat()
                    new_df["data_quality_score"] = None
                    validator = DataQualityValidator()
                    raw = normalize_ohlcv(new_df)
                    clean, report = validator.validate(raw)
                    if report.action != "pause":
                        self.storage.save_ohlcv(clean)
                    return True
            # Fallback ke Yahoo Finance untuk data terbaru
            adapter = YahooFinanceAdapter()
            result = adapter.fetch_incremental(ticker, last_timestamp=last_ts)
            if result["status"] == "ok":
                validator = DataQualityValidator()
                raw = normalize_ohlcv(result["records"])
                clean, report = validator.validate(raw)
                if report.action != "pause":
                    self.storage.save_ohlcv(clean)
            return True
        # SQLite kosong — coba Parquet archive dulu
        arch_df = self.archive.load_ohlcv(ticker)
        if not arch_df.empty:
            arch_df = arch_df.reset_index()
            arch_df["ticker"] = ticker
            arch_df["asset_class"] = "equity"
            arch_df["exchange"] = "INDO" if ticker.endswith(".JK") else "GLOBAL"
            arch_df["timeframe"] = "1d"
            arch_df["source"] = "archive"
            arch_df["ingested_at"] = datetime.now(UTC).isoformat()
            arch_df["data_quality_score"] = None
            validator = DataQualityValidator()
            raw = normalize_ohlcv(arch_df)
            clean, report = validator.validate(raw)
            if report.action != "pause":
                self.storage.save_ohlcv(clean)
            return True
        # Fallback terakhir: Yahoo Finance
        adapter = YahooFinanceAdapter()
        result = adapter.fetch(ticker, period=period)
        if result["status"] == "ok":
            validator = DataQualityValidator()
            raw = normalize_ohlcv(result["records"])
            clean, report = validator.validate(raw)
            if report.action != "pause":
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
        self.corporate.fetch(ticker)
        self.storage.update_adjusted_close(ticker)

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

        as_of = datetime.now(UTC).isoformat()
        for engine, res in results.items():
            if res.get("status") in ("ok", "warning", "degraded", "failed") and res.get("score") is not None:
                self.storage.save_score(
                    ticker,
                    engine,
                    res["score"],
                    res.get("breakdown", {}),
                    as_of=as_of,
                )
            # Store weight_multiplier for decision engine to use
            if res.get("weight_multiplier") is not None and res.get("breakdown") is not None:
                res["breakdown"]["_weight_multiplier"] = res["weight_multiplier"]

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
