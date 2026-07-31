"""FastAPI API dasar (Phase 1)."""

import sys
import os
import secrets
import time
import logging
import importlib
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pandas as pd
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
from trading_system.config import TRADING_CAPITAL

app = FastAPI(title="Trading System API", version="0.1.0")

# CORS middleware — allow frontend (port 3000) and any origin in dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

storage = DataStorage()

# API Key authentication (optional in dev — WAJIB non-kosong jika ENV=production).
_API_KEY = os.getenv("API_KEY", "")
_ENV = os.getenv("ENV", "development").lower()

if _ENV == "production" and not _API_KEY:
    # Fail-fast: jangan biarkan production berjalan tanpa autentikasi (§3.5).
    raise RuntimeError(
        "API_KEY wajib diisi saat ENV=production. Set variabel lingkungan API_KEY "
        "sebelum menjalankan server di production."
    )

# Endpoint sensitif yang mengubah perilaku trading runtime — selalu wajib API key
# (bukan opsional) meskipun ENV bukan production, karena dampaknya langsung ke
# eksekusi order nyata (§3.5).
_SENSITIVE_PATHS = {"/api/execution/toggle", "/api/rebalance/toggle"}


def _valid_api_key(provided: str) -> bool:
    """Bandingkan API key dengan constant-time comparison (anti timing-attack)."""
    return bool(_API_KEY) and secrets.compare_digest(provided, _API_KEY)


@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    """Validate API key if API_KEY env var is set. Skip for health/root.

    WebSocket handshake (`/ws/*`) divalidasi terpisah di dalam handler karena
    header custom tidak selalu tersedia saat upgrade koneksi; lihat `ws_engines`.
    """
    path = request.url.path
    if path in ("/", "/api/health") or path.startswith("/ws/"):
        return await call_next(request)

    if path in _SENSITIVE_PATHS and not _API_KEY:
        # Endpoint sensitif tidak boleh berjalan tanpa proteksi API key sama sekali.
        return JSONResponse(status_code=503, content={"detail": "API_KEY belum dikonfigurasi di server; endpoint ini dinonaktifkan demi keamanan."})

    if _API_KEY:
        provided = request.headers.get("X-API-Key", "")
        if not _valid_api_key(provided):
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})
    return await call_next(request)

# Rate limiting (in-memory, per-IP). NOTE: tidak bekerja lintas proses untuk
# multi-worker (uvicorn --workers > 1) karena state in-memory — gunakan Redis/
# slowapi untuk deployment multi-worker (§3.5 P2 follow-up).
_rate_limit_store: dict[str, list[float]] = {}
_RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "60"))  # requests per window
_RATE_LIMIT_WINDOW = 60  # seconds
_rate_limit_last_cleanup = time.time()
_RATE_LIMIT_CLEANUP_INTERVAL = 300  # seconds


def _cleanup_idle_rate_limit_entries(now: float) -> None:
    """Buang entri IP yang sudah tidak aktif agar dict tidak bocor memori."""
    global _rate_limit_last_cleanup
    if now - _rate_limit_last_cleanup < _RATE_LIMIT_CLEANUP_INTERVAL:
        return
    idle_ips = [
        ip for ip, timestamps in _rate_limit_store.items()
        if not timestamps or now - timestamps[-1] > _RATE_LIMIT_WINDOW
    ]
    for ip in idle_ips:
        del _rate_limit_store[ip]
    _rate_limit_last_cleanup = now


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    """Simple in-memory rate limiting per client IP."""
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    _cleanup_idle_rate_limit_entries(now)
    if client_ip not in _rate_limit_store:
        _rate_limit_store[client_ip] = []
    # Remove old entries
    _rate_limit_store[client_ip] = [t for t in _rate_limit_store[client_ip] if now - t < _RATE_LIMIT_WINDOW]
    if len(_rate_limit_store[client_ip]) >= _RATE_LIMIT_MAX:
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Try again later."})
    _rate_limit_store[client_ip].append(now)
    return await call_next(request)


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


@app.get("/api/indicators/{ticker}")
def get_indicators(ticker: str):
    """Return OHLCV with computed technical indicators (RSI, MACD, MA, Bollinger)."""
    from trading_system.analysis.technical import TechnicalAnalysisEngine

    df = storage.load_ohlcv(ticker)
    if df.empty:
        raise HTTPException(status_code=404, detail="Data not found")
    engine = TechnicalAnalysisEngine()
    engine.ohlcv = df
    df_with_indicators = engine.compute_indicators()
    records = []
    for idx, row in df_with_indicators.iterrows():
        record = {
            "time": str(idx).split("T")[0] if hasattr(idx, "split") else str(idx),
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"],
        }
        if "rsi" in row and not pd.isna(row.get("rsi")):
            record["rsi"] = float(row["rsi"])
        if "macd" in row and not pd.isna(row.get("macd")):
            record["macd"] = float(row["macd"])
        if "macd_signal" in row and not pd.isna(row.get("macd_signal")):
            record["macd_signal"] = float(row["macd_signal"])
        if "ma_20" in row and not pd.isna(row.get("ma_20")):
            record["ma_20"] = float(row["ma_20"])
        if "ma_50" in row and not pd.isna(row.get("ma_50")):
            record["ma_50"] = float(row["ma_50"])
        if "bb_upper" in row and not pd.isna(row.get("bb_upper")):
            record["bb_upper"] = float(row["bb_upper"])
        if "bb_lower" in row and not pd.isna(row.get("bb_lower")):
            record["bb_lower"] = float(row["bb_lower"])
        records.append(record)
    return {"ticker": ticker, "count": len(records), "data": records}


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
            if report.action not in ("pause",):
                storage.save_ohlcv(clean)
            results.append({"ticker": t, "rows": len(clean), "quality": report.data_quality_score, "tier": report.tier, "action": report.action})
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
    cash = payload.get("capital", TRADING_CAPITAL)
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
    capital = payload.get("capital", TRADING_CAPITAL)
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


@app.post("/api/backtest/monte-carlo")
def run_monte_carlo(payload: dict):
    """Run Monte Carlo simulation on historical returns of a ticker."""
    from trading_system.backtest.metrics import monte_carlo_simulation

    ticker = payload.get("ticker")
    n_simulations = payload.get("n_simulations", 1000)
    n_periods = payload.get("n_periods", 252)
    capital = payload.get("capital", TRADING_CAPITAL)
    block_size = payload.get("block_size")
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker required")

    df = storage.load_ohlcv(ticker)
    if df.empty:
        raise HTTPException(status_code=404, detail="Data not found")

    returns = df["close"].pct_change().dropna()
    result = monte_carlo_simulation(returns, n_simulations=n_simulations, n_periods=n_periods, initial_capital=capital, block_size=block_size)
    return {"ticker": ticker, **result}


@app.post("/api/backtest/walk-forward")
def run_walk_forward(payload: dict):
    """Run walk-forward analysis for a strategy."""
    from trading_system.backtest.metrics import walk_forward_analysis

    ticker = payload.get("ticker")
    strategy_name = payload.get("strategy", "buy_and_hold")
    n_splits = payload.get("n_splits", 5)
    train_size = payload.get("train_size", 252)
    test_size = payload.get("test_size", 63)
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker required")

    df = storage.load_ohlcv(ticker)
    if df.empty:
        raise HTTPException(status_code=404, detail="Data not found")

    if strategy_name == "buy_and_hold":
        factory = lambda: BuyAndHold()
    elif strategy_name == "ma_crossover":
        factory = lambda: MovingAverageCrossover(20, 50)
    else:
        raise HTTPException(status_code=400, detail="Unknown strategy")

    result = walk_forward_analysis(df, factory, n_splits=n_splits, train_size=train_size, test_size=test_size)
    return {"ticker": ticker, "strategy": strategy_name, **result}


@app.get("/api/positions")
def get_positions():
    """Get all open positions."""
    positions = storage.get_all_open_positions()
    return {"positions": positions, "count": len(positions)}


@app.get("/api/positions/{ticker}")
def get_position(ticker: str):
    """Get open position for a specific ticker."""
    position = storage.get_open_position(ticker)
    if not position:
        raise HTTPException(status_code=404, detail=f"No open position for {ticker}")
    return position


@app.get("/api/orders")
def get_orders(ticker: str | None = None, limit: int = 100):
    """Get order history."""
    orders = storage.get_orders(ticker=ticker, limit=limit)
    return {"orders": orders, "count": len(orders)}


@app.post("/api/execution/run")
def run_execution_cycle(payload: dict):
    """Run one execution cycle (manual trigger)."""
    from trading_system.execution.automated import AutomatedExecutionEngine

    tickers = payload.get("tickers")
    engine = AutomatedExecutionEngine(storage=storage)
    results = engine.run_once(tickers)
    return {"results": results, "count": len(results)}


@app.post("/api/rebalance")
def trigger_rebalance(payload: dict | None = None):
    """Trigger portfolio rebalancing manually."""
    from trading_system.portfolio.rebalancer import PortfolioRebalancer

    rebalancer = PortfolioRebalancer(storage=storage)
    # Temporarily enable if called via API
    if not rebalancer.rebalance_enabled:
        rebalancer.rebalance_enabled = True
    results = rebalancer.run_rebalance()
    return {"status": "ok", "orders": results, "count": len(results)}


@app.get("/api/rebalance/status")
def get_rebalance_status():
    """Get current rebalance status (weights, drift, config)."""
    from trading_system.portfolio.rebalancer import PortfolioRebalancer

    rebalancer = PortfolioRebalancer(storage=storage)
    return rebalancer.get_rebalance_status()


@app.get("/api/execution/logs")
def get_execution_logs(limit: int = 20):
    """Get recent execution logs (orders + audit events) for dashboard display."""
    orders = storage.get_orders(limit=limit)
    logs = []
    for o in orders:
        logs.append({
            "type": "ORDER",
            "ticker": o.get("ticker", ""),
            "action": o.get("order_type", ""),
            "quantity": o.get("quantity", 0),
            "price": o.get("price", 0),
            "total_value": o.get("total_value", 0),
            "fee": o.get("fee", 0),
            "status": o.get("status", ""),
            "trigger": o.get("trigger", "MANUAL"),
            "timestamp": o.get("created_at", ""),
            "details": f"{o.get('order_style', 'MARKET')} order",
        })

    # Also get recent audit events for decision signals
    import sqlite3
    from trading_system.config import DB_PATH
    try:
        conn = sqlite3.connect(DB_PATH)
        audit_rows = conn.execute(
            "SELECT event_type, payload, timestamp FROM audit_log WHERE event_type LIKE 'decision.%' ORDER BY rowid DESC LIMIT 10"
        ).fetchall()
        conn.close()

        import json
        for event_type, payload_str, ts in audit_rows:
            try:
                payload = json.loads(payload_str)
                logs.append({
                    "type": "SIGNAL",
                    "ticker": payload.get("ticker", ""),
                    "action": payload.get("action", ""),
                    "conviction": payload.get("conviction_score", 0),
                    "status": "GENERATED",
                    "timestamp": ts,
                    "details": f"Conviction: {payload.get('conviction_score', 'N/A')}",
                })
            except Exception:
                pass
    except Exception:
        pass

    # Sort by timestamp descending
    logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return {"logs": logs[:limit], "count": len(logs[:limit])}


# ====================== RUNTIME TOGGLES ======================
# In-memory runtime config (persists until server restart).
# On startup, reads from .env. Can be toggled via API without restart.

_runtime_config = {
    "auto_trade_enabled": os.getenv("AUTO_TRADE_ENABLED", "false").lower() == "true",
    "rebalance_enabled": os.getenv("REBALANCE_ENABLED", "false").lower() == "true",
}


@app.get("/api/execution/toggle")
def get_auto_trade_toggle():
    """Get current auto-trade toggle status."""
    return {
        "auto_trade_enabled": _runtime_config["auto_trade_enabled"],
        "capital": TRADING_CAPITAL,
        "risk_per_trade": float(os.getenv("RISK_PER_TRADE", "0.01")),
        "daily_loss_limit": float(os.getenv("DAILY_LOSS_LIMIT", "0")),
    }


@app.post("/api/execution/toggle")
def set_auto_trade_toggle(payload: dict):
    """Toggle auto-trade on/off at runtime (no server restart needed).

    Body: {"enabled": true/false}
    """
    enabled = payload.get("enabled", False)
    _runtime_config["auto_trade_enabled"] = bool(enabled)

    # Also update os.environ so new AutomatedExecutionEngine instances pick it up
    os.environ["AUTO_TRADE_ENABLED"] = "true" if enabled else "false"

    status = "ENABLED" if enabled else "DISABLED"
    logger = logging.getLogger("api.toggle")
    logger.warning(f"Auto-trade toggled {status} via API")

    return {
        "auto_trade_enabled": _runtime_config["auto_trade_enabled"],
        "message": f"Auto-trade {status}. {'Orders will execute automatically.' if enabled else 'Monitor mode only — no real execution.'}",
    }


@app.get("/api/rebalance/toggle")
def get_rebalance_toggle():
    """Get current rebalance toggle status."""
    return {
        "rebalance_enabled": _runtime_config["rebalance_enabled"],
        "frequency": os.getenv("REBALANCE_FREQUENCY", "monthly"),
        "target_weights": os.getenv("REBALANCE_TARGET_WEIGHTS", ""),
    }


@app.post("/api/rebalance/toggle")
def set_rebalance_toggle(payload: dict):
    """Toggle rebalance on/off at runtime (no server restart needed).

    Body: {"enabled": true/false}
    Optional: {"frequency": "daily|weekly|monthly", "target_weights": {"BBCA.JK": 0.4, ...}}
    """
    enabled = payload.get("enabled", False)
    _runtime_config["rebalance_enabled"] = bool(enabled)
    os.environ["REBALANCE_ENABLED"] = "true" if enabled else "false"

    # Optional: update frequency
    if "frequency" in payload:
        freq = payload["frequency"]
        if freq in ("daily", "weekly", "monthly"):
            os.environ["REBALANCE_FREQUENCY"] = freq

    # Optional: update target weights
    if "target_weights" in payload:
        import json
        os.environ["REBALANCE_TARGET_WEIGHTS"] = json.dumps(payload["target_weights"])

    status = "ENABLED" if enabled else "DISABLED"
    logger = logging.getLogger("api.toggle")
    logger.warning(f"Rebalance toggled {status} via API")

    return {
        "rebalance_enabled": _runtime_config["rebalance_enabled"],
        "frequency": os.getenv("REBALANCE_FREQUENCY", "monthly"),
        "message": f"Rebalance {status}.",
    }


# ====================== PERFORMANCE ANALYTICS ======================
@app.get("/api/performance")
def get_performance(period: str = "1M"):
    """Get portfolio performance metrics: equity curve, Sharpe, drawdown, win rate."""
    from trading_system.portfolio.performance import PerformanceAnalytics
    analytics = PerformanceAnalytics(storage=storage)
    return analytics.get_performance(period=period)


@app.post("/api/performance/snapshot")
def save_performance_snapshot():
    """Save a daily equity snapshot manually."""
    from trading_system.portfolio.performance import PerformanceAnalytics
    analytics = PerformanceAnalytics(storage=storage)
    equity = analytics.save_daily_snapshot()
    return {"status": "ok", "equity": equity}


# ====================== WATCHLIST ======================
@app.get("/api/tickers")
def list_tickers():
    """List all tickers in the database."""
    tickers = storage.list_tickers()
    return {"tickers": tickers, "count": len(tickers)}


@app.get("/api/watchlist")
def get_watchlist():
    """Get favorite tickers from watchlist."""
    items = storage.get_watchlist(favorites_only=True)
    return {"tickers": [item["ticker"] for item in items], "count": len(items)}


@app.post("/api/watchlist/{ticker}")
def toggle_watchlist(ticker: str):
    """Toggle favorite status for a ticker."""
    is_fav = storage.toggle_watchlist(ticker)
    return {"ticker": ticker, "is_favorite": is_fav}


@app.get("/api/watchlist/all")
def get_full_watchlist():
    """Get full watchlist with details."""
    items = storage.get_watchlist(favorites_only=False)
    return {"items": items, "count": len(items)}


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
    {"name": "automated_execution", "module": "trading_system.execution.automated", "cls": "AutomatedExecutionEngine"},
    {"name": "rebalancer", "module": "trading_system.portfolio.rebalancer", "cls": "PortfolioRebalancer"},
    {"name": "performance_analytics", "module": "trading_system.portfolio.performance", "cls": "PerformanceAnalytics"},
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


@app.websocket("/ws/live")
async def ws_engines(websocket: WebSocket):
    # Auth: jika API_KEY dikonfigurasi, wajibkan token yang cocok via query
    # param `?token=` atau header `X-API-Key` pada handshake. Sebelumnya
    # semua path /ws/* di-skip total dari pengecekan API key (§3.5), sehingga
    # /ws/live mengekspos status seluruh engine ke siapa pun tanpa autentikasi.
    if _API_KEY:
        provided = websocket.query_params.get("token") or websocket.headers.get("x-api-key", "")
        if not _valid_api_key(provided or ""):
            await websocket.close(code=4401)
            return

    await websocket.accept()
    try:
        while True:
            data = _build_engines_status()
            await websocket.send_json(data)
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass


# ====================== AI LEARNING ======================
@app.post("/api/ai/train")
def train_ai_weights(ticker: str | None = None):
    """Train Linear Regression to optimize factor weights from historical data."""
    from trading_system.ai_learning.engine import AILearningEngine
    engine = AILearningEngine()
    result = engine.train_linear_regression(ticker=ticker)
    return result


@app.get("/api/ai/weights")
def get_ai_weights(ticker: str | None = None):
    """Get current AI-optimized weights."""
    from trading_system.ai_learning.engine import AILearningEngine
    engine = AILearningEngine()
    weights = engine.storage.get_ai_weights(ticker=ticker, max_age_days=30)
    if weights is None:
        return {"status": "no_weights", "message": "No trained weights found. Run /api/ai/train first."}
    return {"status": "ok", "weights": weights}


# ====================== DAILY RISK METRICS ======================
@app.get("/api/risk/daily")
def get_daily_risk(limit: int = 30):
    """Get daily portfolio risk metrics (VaR, CVaR, max drawdown)."""
    from trading_system.risk.engine import RiskEngine
    engine = RiskEngine()
    metrics = engine.storage.get_daily_risk_metrics(limit=limit)
    return {"status": "ok", "metrics": metrics, "count": len(metrics)}


@app.post("/api/risk/refresh")
def refresh_daily_risk():
    """Recalculate and save daily portfolio risk metrics."""
    from trading_system.risk.engine import RiskEngine
    engine = RiskEngine()
    result = engine.save_daily_risk()
    return result


# ====================== SENTIMENT NLP ======================
@app.get("/api/sentiment/{ticker}")
def get_sentiment(ticker: str):
    """Get news-based sentiment analysis for a ticker (Indonesian NLP)."""
    from trading_system.sentiment.engine import SentimentEngine
    engine = SentimentEngine()
    result = engine.compute(ticker)
    return result


if __name__ == "__main__":
    from trading_system.utils.logging_config import setup_logging
    setup_logging()
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
