"""FastAPI API dasar (Phase 1)."""

import sys
import time
import importlib
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect

from trading_system.data.storage import DataStorage
from trading_system.data.acquisition import YahooFinanceAdapter, normalize_ohlcv
from trading_system.data.validation import DataQualityValidator
from trading_system.backtest.engine import BacktestEngine
from trading_system.backtest.strategies import BuyAndHold, MovingAverageCrossover
from trading_system.analysis.pipeline import AnalysisPipeline
from trading_system.corporate.actions import CorporateActionEngine
from trading_system.intelligence.relationship import MarketRelationshipEngine
from trading_system.decision.engine import DecisionEngine, DEFAULT_WEIGHTS
from trading_system.xai.engine import ExplainableAIEngine
from trading_system.monitoring.engine import MonitoringEngine
from trading_system.paper_trading.engine import PaperTradingEngine
from trading_system.ai_learning.engine import AILearningEngine

app = FastAPI(title="Trading System API", version="0.1.0")

storage = DataStorage()


@app.get("/")
def root():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/health")
def health():
    return storage.get_source_health().to_dict(orient="records")


@app.get("/api/data/{category}")
def get_data(category: str, ticker: str, start: str | None = None, end: str | None = None):
    if category != "ohlcv":
        raise HTTPException(status_code=400, detail="Only ohlcv supported in Phase 1")
    df = storage.load_ohlcv(ticker, start=start, end=end)
    if df.empty:
        raise HTTPException(status_code=404, detail="Data not found")
    return {"ticker": ticker, "count": len(df), "data": df.reset_index().to_dict(orient="records")}


@app.post("/api/fetch")
def fetch_data(payload: dict):
    tickers = payload.get("tickers", [])
    period = payload.get("period", "2y")
    adapter = YahooFinanceAdapter()
    validator = DataQualityValidator()
    results = []
    for t in tickers:
        result = adapter.fetch(t, period=period)
        if result["status"] == "ok":
            raw = normalize_ohlcv(result["records"])
            clean, report = validator.validate(raw)
            if report.action != "pause":
                storage.save_ohlcv(clean)
            results.append({"ticker": t, "rows": len(clean), "quality": report.data_quality_score})
        else:
            results.append({"ticker": t, "error": result["message"]})
    return {"results": results}


@app.get("/api/scores/{ticker}")
def get_scores(ticker: str):
    df_scores = storage.load_scores(ticker)
    if df_scores.empty:
        return {
            "ticker": ticker,
            "computed": False,
            "scores": {},
        }
    latest = df_scores.drop_duplicates("engine").set_index("engine")
    return {
        "ticker": ticker,
        "computed": True,
        "scores": {idx: row["score"] for idx, row in latest.iterrows()},
        "details": [
            {"engine": idx, "score": row["score"], "as_of": row["as_of"]}
            for idx, row in latest.iterrows()
        ],
    }


@app.post("/api/scores/compute")
def compute_scores(payload: dict):
    ticker = payload.get("ticker")
    period = payload.get("period", "2y")
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker required")
    pipeline = AnalysisPipeline(storage=storage)
    result = pipeline.compute(ticker, period)
    if result["status"] == "error":
        raise HTTPException(status_code=404, detail=result["message"])
    return result


@app.get("/api/corporate/{ticker}")
def get_corporate_actions(ticker: str):
    corp = CorporateActionEngine(storage=storage)
    result = corp.fetch(ticker)
    if result["status"] == "error":
        raise HTTPException(status_code=404, detail=result["message"])
    return result


@app.get("/api/relationship/{ticker}")
def get_relationship(ticker: str, window: int = 60):
    rel = MarketRelationshipEngine(storage=storage, window=window)
    result = rel.compute(ticker)
    if result["status"] == "error":
        raise HTTPException(status_code=404, detail=result["message"])
    return result


@app.get("/api/recommend/{ticker}")
def get_recommendation(ticker: str):
    engine = DecisionEngine(storage=storage)
    result = engine.recommend(ticker)
    if result["status"] == "error":
        raise HTTPException(status_code=404, detail=result["message"])
    return result


@app.post("/api/recommend")
def post_recommendation(payload: dict):
    ticker = payload.get("ticker")
    weights = payload.get("weights", DEFAULT_WEIGHTS)
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker required")
    engine = DecisionEngine(storage=storage)
    result = engine.recommend(ticker, weights=weights)
    if result["status"] == "error":
        raise HTTPException(status_code=404, detail=result["message"])
    return result


@app.get("/api/explain/{ticker}")
def explain_recommendation(ticker: str):
    dec = DecisionEngine(storage=storage).recommend(ticker)
    if dec["status"] == "error":
        raise HTTPException(status_code=404, detail=dec["message"])
    xai = ExplainableAIEngine(storage=storage)
    return xai.explain(ticker, dec["recommendation"])


@app.post("/api/paper-trade")
def paper_trade(payload: dict):
    ticker = payload.get("ticker")
    cash = payload.get("capital", 1_000_000_000)
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker required")
    engine = PaperTradingEngine(storage=storage, cash=cash)
    result = engine.simulate(ticker)
    if result["status"] == "error":
        raise HTTPException(status_code=404, detail=result["message"])
    return result


@app.get("/api/monitor")
def monitor():
    return MonitoringEngine(storage=storage).health()


@app.get("/api/factor-weights/{ticker}")
def factor_weights(ticker: str, regime: str | None = None):
    return {"ticker": ticker, "regime": regime, "weights": AILearningEngine(storage=storage).get_factor_weights(ticker, regime)}


@app.post("/api/backtest")
def run_backtest(payload: dict):
    ticker = payload.get("ticker")
    strategy_name = payload.get("strategy", "buy_and_hold")
    capital = payload.get("capital", 1_000_000_000)
    engine = BacktestEngine(storage=storage)
    if strategy_name == "buy_and_hold":
        strategy = BuyAndHold()
    elif strategy_name == "ma_crossover":
        strategy = MovingAverageCrossover(20, 50)
    else:
        raise HTTPException(status_code=400, detail="Unknown strategy")
    result = engine.run(ticker, strategy, initial_capital=capital)
    if result["status"] == "error":
        raise HTTPException(status_code=404, detail=result["message"])
    return {
        "ticker": ticker,
        "strategy": result["strategy"],
        "final_equity": result["final_equity"],
        "metrics": result["metrics"],
        "trade_count": len(result["trade_history"]),
    }


ENGINE_REGISTRY = [
    {"name": "technical", "module": "trading_system.analysis.technical", "cls": "TechnicalAnalysisEngine"},
    {"name": "fundamental", "module": "trading_system.analysis.fundamental", "cls": "FundamentalAnalysisEngine"},
    {"name": "macro", "module": "trading_system.analysis.macro", "cls": "MacroEconomicEngine"},
    {"name": "global_market", "module": "trading_system.analysis.global_market", "cls": "GlobalMarketEngine"},
    {"name": "relationship", "module": "trading_system.intelligence.relationship", "cls": "MarketRelationshipEngine"},
    {"name": "sentiment", "module": "trading_system.sentiment.engine", "cls": "SentimentEngine"},
    {"name": "corporate", "module": "trading_system.corporate.actions", "cls": "CorporateActionEngine"},
    {"name": "decision", "module": "trading_system.decision.engine", "cls": "DecisionEngine"},
    {"name": "xai", "module": "trading_system.xai.engine", "cls": "ExplainableAIEngine"},
    {"name": "backtest", "module": "trading_system.backtest.engine", "cls": "BacktestEngine"},
    {"name": "paper_trading", "module": "trading_system.paper_trading.engine", "cls": "PaperTradingEngine"},
    {"name": "monitoring", "module": "trading_system.monitoring.engine", "cls": "MonitoringEngine"},
    {"name": "ai_learning", "module": "trading_system.ai_learning.engine", "cls": "AILearningEngine"},
    {"name": "risk", "module": "trading_system.risk.engine", "cls": "RiskEngine"},
    {"name": "execution", "module": "trading_system.execution.engine", "cls": "ExecutionEngine"},
]


def _build_engines_status() -> dict:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    results = []
    for meta in ENGINE_REGISTRY:
        t0 = time.time()
        try:
            mod = importlib.import_module(meta["module"])
            Klass = getattr(mod, meta["cls"])
            try:
                obj = Klass(storage=storage)
            except TypeError:
                obj = Klass()
            last_run = None
            status = "healthy"
            extra = {}
            if meta["name"] == "monitoring":
                health = obj.health()
                last_run = health.get("timestamp") or now
                if health.get("status") != "ok":
                    status = "warning"
                extra = {"tickers_in_db": len(health.get("tickers_in_db", [])), "score_count": health.get("score_count", 0)}
            else:
                df = storage.load_scores(engine=meta["name"])
                if not df.empty:
                    last_run = df.iloc[0]["as_of"]
                    extra = {"latest_score": float(df.iloc[0]["score"]), "sample_ticker": df.iloc[0]["ticker"]}
                else:
                    status = "idle"
            results.append({
                "name": meta["name"],
                "status": status,
                "last_run": last_run,
                "latency_ms": round((time.time() - t0) * 1000, 2),
                **extra,
            })
        except Exception as e:
            results.append({
                "name": meta["name"],
                "status": "error",
                "last_run": None,
                "latency_ms": round((time.time() - t0) * 1000, 2),
                "error": str(e),
            })
    return {"timestamp": now, "engines": results}


@app.get("/api/engines")
def get_engines():
    return _build_engines_status()


@app.websocket("/ws/engines")
async def ws_engines(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = _build_engines_status()
            await websocket.send_json(data)
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
