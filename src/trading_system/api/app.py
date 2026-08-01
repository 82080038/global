"""FastAPI API dasar (Phase 1)."""

import asyncio
import importlib
import json
import logging
import math
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from datetime import UTC

from fastapi import Body, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


def _sanitize_nan(obj):
    """Recursively replace NaN/Inf with None for JSON compliance."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_nan(v) for v in obj]
    return obj


class SanitizedJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return json.dumps(
            _sanitize_nan(content),
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
        ).encode("utf-8")

from trading_system.ai_learning.engine import AILearningEngine
from trading_system.analysis.pipeline import AnalysisPipeline
from trading_system.backtest.engine import BacktestEngine
from trading_system.backtest.strategies import BuyAndHold, ConvictionStrategy, MovingAverageCrossover
from trading_system.config import TRADING_CAPITAL
from trading_system.corporate.actions import CorporateActionEngine
from trading_system.data.acquisition import YahooFinanceAdapter, normalize_ohlcv
from trading_system.data.storage import DataStorage
from trading_system.data.validation import DataQualityValidator
from trading_system.decision.engine import DEFAULT_WEIGHTS, DecisionEngine
from trading_system.analysis.relationship import MarketRelationshipEngine
from trading_system.monitoring.engine import MonitoringEngine
from trading_system.paper_trading.engine import PaperTradingEngine
from trading_system.xai.engine import ExplainableAIEngine

app = FastAPI(title="Trading System API", version="0.1.8", default_response_class=SanitizedJSONResponse)

# Global exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unexpected errors."""
    logging.error(f"Unexpected error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Internal server error",
            "detail": str(exc) if os.getenv("ENV") == "development" else "An unexpected error occurred",
        },
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handler for HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "message": exc.detail,
        },
    )

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
_SENSITIVE_PATHS = {
    "/api/execution/toggle",
    "/api/rebalance/toggle",
    "/api/execution/run",
    "/api/rebalance",
    "/api/fetch",
    "/api/scores/{ticker}",
    "/api/orders",
    "/api/audit",
    "/api/positions/{position_id}",
    "/api/ai/weights",
    "/api/performance/snapshot",
    "/api/risk/daily",
    "/api/archive/{ticker}",
    "/api/relationships",
    "/api/corporate-actions/{ticker}",
    "/api/news",
}

# DELETE methods are always sensitive regardless of path
_DELETE_METHOD = "DELETE"


def _valid_api_key(provided: str) -> bool:
    """Bandingkan API key dengan constant-time comparison (anti timing-attack)."""
    return bool(_API_KEY) and secrets.compare_digest(provided, _API_KEY)


def _cors_error_response(status_code: int, detail: str, request: Request) -> JSONResponse:
    """Build JSONResponse with CORS headers for middleware-level error responses.

    Middleware `api_key_auth` dan `rate_limit` berada di luar CORSMiddleware
    (di-insert setelahnya via @app.middleware), sehingga response yang di-return
    langsung dari middleware tidak melewati CORSMiddleware dan tidak mendapat
    header Access-Control-Allow-Origin. Browser lalu memblokir response dengan
    CORS error, menyembunyikan pesan error sebenarnya (§3.5).
    """
    origin = request.headers.get("origin", "")
    allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    headers = {}
    if origin in allowed_origins:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Access-Control-Allow-Methods"] = "*"
        headers["Access-Control-Allow-Headers"] = "*"
    return JSONResponse(status_code=status_code, content={"detail": detail}, headers=headers)


def _finite_or_none(v):
    """Convert a numeric value to float, returning None for NaN/inf.

    Python's stdlib JSON serializer emits `NaN`/`Infinity` tokens which are
    invalid JSON per RFC 8259 and rejected by strict parsers (and the browser
    `fetch().json()` in some cases). Pandas `pd.isna()` returns False for inf,
    so callers that only check `pd.isna` still leak inf into responses.
    """
    import math
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _sanitize_records(records: list) -> list:
    """Replace NaN/inf floats in a list of dict records with None.

    Used for endpoints that serialize pandas DataFrames via `to_dict` — those
    can contain NaN (from missing indicators) or inf (from division by zero in
    indicator math) which would produce invalid JSON.
    """
    import math
    out = []
    for rec in records:
        clean = {}
        for k, v in rec.items():
            if isinstance(v, float) and not math.isfinite(v):
                clean[k] = None
            else:
                clean[k] = v
        out.append(clean)
    return out


def _clamp_pagination(page: int, limit: int, max_limit: int = 1000) -> tuple[int, int]:
    """Validate and clamp pagination params to prevent negative offsets and DoS
    via huge limits. Negative `page` would yield negative `iloc` offsets (which
    in pandas counts from the end of the frame, silently returning wrong data);
    a zero/negative `limit` produces an empty slice or division-by-zero in page
    count math.
    """
    if page < 1:
        page = 1
    if limit < 1:
        limit = 500
    if limit > max_limit:
        limit = max_limit
    return page, limit


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """Add correlation ID to every request for observability and audit trail.

    Reads X-Correlation-ID header if present, otherwise generates a new UUID.
    The correlation ID is added to response headers and stored in request state
    so downstream handlers can include it in logs and audit entries.
    """
    import uuid as _uuid

    correlation_id = request.headers.get("X-Correlation-ID") or str(_uuid.uuid4())
    request.state.correlation_id = correlation_id

    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    """Validate API key if API_KEY env var is set. Skip for health/root.

    WebSocket handshake (`/ws/*`) divalidasi terpisah di dalam handler karena
    header custom tidak selalu tersedia saat upgrade koneksi; lihat `ws_engines`.
    """
    path = request.url.path
    method = request.method
    # Skip auth for health/root and CORS preflight (OPTIONS) requests.
    # Preflight requests don't carry credentials and must be allowed to reach
    # CORSMiddleware, otherwise the browser blocks the actual request (§3.5).
    if path in ("/", "/api/health") or path.startswith("/ws/") or method == "OPTIONS":
        return await call_next(request)

    # DELETE methods are always sensitive (destructive operations)
    # Also check parameterized paths like /api/data/{category} by prefix matching
    is_sensitive = method == _DELETE_METHOD
    if not is_sensitive:
        for sp in _SENSITIVE_PATHS:
            if "{" in sp:
                # Parameterized path: match prefix before the {param} segment
                prefix = sp.split("{")[0].rstrip("/")
                if path.startswith(prefix + "/"):
                    is_sensitive = True
                    break
            elif path == sp:
                is_sensitive = True
                break

    if is_sensitive and not _API_KEY:
        return _cors_error_response(503, "API_KEY belum dikonfigurasi di server; endpoint ini dinonaktifkan demi keamanan.", request)

    if _API_KEY:
        provided = request.headers.get("X-API-Key", "")
        if not _valid_api_key(provided):
            return _cors_error_response(401, "Invalid or missing API key", request)
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
        return _cors_error_response(429, "Rate limit exceeded. Try again later.", request)
    _rate_limit_store[client_ip].append(now)
    return await call_next(request)


@app.get("/")
def root():
    return {"status": "ok", "version": app.version}


@app.get("/api/health")
def health():
    return storage.get_source_health().to_dict(orient="records")


@app.get("/api/data/{category}")
def get_data(category: str, ticker: str, start: str | None = None, end: str | None = None, page: int = 1, limit: int = 500):
    if category != "ohlcv":
        raise HTTPException(status_code=400, detail="Only ohlcv supported in Phase 1")
    df = storage.load_ohlcv(ticker, start=start, end=end)
    if df.empty:
        raise HTTPException(status_code=404, detail="Data not found")
    page, limit = _clamp_pagination(page, limit)
    total = len(df)
    offset = (page - 1) * limit
    df_page = df.iloc[offset:offset + limit]
    records = _sanitize_records(df_page.reset_index().to_dict(orient="records"))
    return {"ticker": ticker, "count": total, "page": page, "limit": limit, "pages": (total + limit - 1) // limit, "data": records}


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
            "open": _finite_or_none(row["open"]),
            "high": _finite_or_none(row["high"]),
            "low": _finite_or_none(row["low"]),
            "close": _finite_or_none(row["close"]),
            "volume": _finite_or_none(row["volume"]),
        }
        for col in ("rsi", "macd", "macd_signal", "ma_20", "ma_50", "bb_upper", "bb_lower"):
            if col in row.index:
                val = _finite_or_none(row.get(col))
                if val is not None:
                    record[col] = val
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
    start = payload.get("start")
    end = payload.get("end")
    engine = BacktestEngine(storage=storage)
    if strategy_name == "buy_and_hold":
        strategy = BuyAndHold()
    elif strategy_name == "ma_crossover":
        strategy = MovingAverageCrossover(20, 50)
    elif strategy_name == "conviction":
        strategy = ConvictionStrategy(storage=storage, ticker=ticker)
    else:
        raise HTTPException(status_code=400, detail="Unknown strategy")
    result = engine.run(ticker, strategy, initial_capital=capital, start=start, end=end)
    if result["status"] == "error":
        raise HTTPException(status_code=404, detail=result["message"])
    metrics = result.get("metrics", {})
    equity_curve = result.get("equity_curve")
    equity_data = []
    if equity_curve is not None and not equity_curve.empty:
        equity_data = [
            {"date": str(idx), "equity": round(float(val), 2)}
            for idx, val in equity_curve.items()
        ]
    return {
        "ticker": ticker,
        "strategy": result["strategy"],
        "final_equity": result["final_equity"],
        "total_return": round(metrics.get("total_return", 0) * 100, 2),
        "sharpe_ratio": metrics.get("sharpe_ratio", 0),
        "max_drawdown": round(abs(metrics.get("max_drawdown", 0)) * 100, 2),
        "win_rate": round(metrics.get("win_rate", 0) * 100, 1),
        "total_trades": len(result["trade_history"]),
        "equity_curve": equity_data,
        "metrics": metrics,
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
    start = payload.get("start")
    end = payload.get("end")
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker required")

    df = storage.load_ohlcv(ticker, start=start, end=end)
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
    start = payload.get("start")
    end = payload.get("end")
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker required")

    df = storage.load_ohlcv(ticker, start=start, end=end)
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


@app.get("/api/portfolio/exposure")
def get_portfolio_exposure():
    """Get portfolio exposure summary: cash, invested, total equity, exposure %."""
    positions = storage.get_all_open_positions()
    invested = sum(
        float(p.get("quantity", 0)) * float(p.get("current_price", p.get("avg_entry_price", 0)))
        for p in positions
    )
    snapshots = storage.get_equity_snapshots(limit=1)
    if snapshots:
        total_equity = float(snapshots[-1].get("equity", 0))
        cash = float(snapshots[-1].get("cash", 0))
    else:
        from trading_system.config import TRADING_CAPITAL
        total_equity = float(TRADING_CAPITAL)
        cash = total_equity - invested
    exposure_pct = round((invested / total_equity * 100) if total_equity > 0 else 0, 2)
    return {
        "cash": round(cash, 2),
        "invested": round(invested, 2),
        "total_equity": round(total_equity, 2),
        "exposure_pct": exposure_pct,
        "position_count": len(positions),
    }


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
def run_execution_cycle(payload: dict = Body(default_factory=dict)):
    """Run one execution cycle (manual trigger)."""
    from trading_system.execution.automated import AutomatedExecutionEngine

    tickers = payload.get("tickers")
    engine = AutomatedExecutionEngine(storage=storage)
    results = engine.run_once(tickers)
    return {"results": results, "count": len(results)}


@app.post("/api/rebalance")
def trigger_rebalance(payload: dict = Body(default_factory=dict)):
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
    audit_rows = []
    # Use a context manager so the connection is always closed even if the
    # query raises (prevents a file-descriptor/connection leak under load).
    try:
        with sqlite3.connect(DB_PATH) as conn:
            audit_rows = conn.execute(
                "SELECT event_type, payload, timestamp FROM audit_log WHERE event_type LIKE 'decision.%' ORDER BY rowid DESC LIMIT 10"
            ).fetchall()
    except sqlite3.Error:
        audit_rows = []

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
def list_tickers(page: int = 1, limit: int = 100):
    """List all tickers in the database with pagination."""
    tickers = storage.list_tickers()
    total = len(tickers)
    offset = (page - 1) * limit
    tickers_page = tickers[offset:offset + limit]
    return {"tickers": tickers_page, "count": total, "page": page, "limit": limit, "pages": (total + limit - 1) // limit}


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
def get_full_watchlist(page: int = 1, limit: int = 100):
    """Get full watchlist with details and pagination."""
    items = storage.get_watchlist(favorites_only=False)
    total = len(items)
    offset = (page - 1) * limit
    items_page = items[offset:offset + limit]
    return {"items": items_page, "count": total, "page": page, "limit": limit, "pages": (total + limit - 1) // limit}


ENGINE_REGISTRY = [
    {"name": "technical", "module": "trading_system.analysis.technical", "cls": "TechnicalAnalysisEngine"},
    {"name": "fundamental", "module": "trading_system.analysis.fundamental", "cls": "FundamentalAnalysisEngine"},
    {"name": "macro", "module": "trading_system.analysis.macro", "cls": "MacroEconomicEngine"},
    {"name": "global_market", "module": "trading_system.analysis.global_market", "cls": "GlobalMarketEngine"},
    {"name": "relationship", "module": "trading_system.analysis.relationship", "cls": "MarketRelationshipEngine"},
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
    from datetime import datetime
    now = datetime.now(UTC).isoformat()
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


# Cache for engine status — avoids recomputing every WS tick (P2-5).
_engines_status_cache: dict | None = None
_engines_status_cache_ts: float = 0
_ENGINES_STATUS_TTL = 3.0  # seconds


def _get_engines_status() -> dict:
    """Return cached engine status, recomputing if older than TTL."""
    global _engines_status_cache, _engines_status_cache_ts
    now = time.time()
    if _engines_status_cache is not None and (now - _engines_status_cache_ts) < _ENGINES_STATUS_TTL:
        return _engines_status_cache
    _engines_status_cache = _build_engines_status()
    _engines_status_cache_ts = now
    return _engines_status_cache


@app.get("/api/engines")
def get_engines():
    return _get_engines_status()


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
            data = _get_engines_status()
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


@app.get("/api/risk/{ticker}")
def get_ticker_risk(ticker: str, capital: float = TRADING_CAPITAL):
    """Get risk analysis for a specific ticker (VaR, position sizing, risk flags)."""
    from trading_system.risk.engine import RiskEngine
    engine = RiskEngine(storage=storage)
    result = engine.analyze(ticker, capital=capital)
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result.get("message", "Risk analysis failed"))
    return result


# ====================== SENTIMENT NLP ======================
@app.get("/api/sentiment/{ticker}")
def get_sentiment(ticker: str):
    """Get news-based sentiment analysis for a ticker (Indonesian NLP)."""
    from trading_system.sentiment.engine import SentimentEngine
    engine = SentimentEngine()
    result = engine.compute(ticker)
    return result


# ====================== AUDIT LOG (Read) ======================
@app.get("/api/audit")
def get_audit_logs(
    event_type: str | None = None,
    actor: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """Get audit log entries with optional filtering and pagination."""
    logs = storage.get_audit_logs(event_type=event_type, actor=actor, limit=limit, offset=offset)
    return {"logs": logs, "count": len(logs)}


# ====================== UPDATE ENDPOINTS (CRUD completeness) ======================
@app.patch("/api/positions/{position_id}")
def update_position(position_id: int, payload: dict):
    """Update position fields (stop_loss, take_profit, trailing_stop_pct, status, etc.)."""
    allowed_fields = {"stop_loss", "take_profit", "trailing_stop_pct", "status",
                      "current_price", "highest_price_since_entry", "quantity",
                      "avg_entry_price", "closed_at"}
    updates = {k: v for k, v in payload.items() if k in allowed_fields}
    if not updates:
        raise HTTPException(status_code=400, detail=f"No valid fields to update. Allowed: {allowed_fields}")
    existing = storage.get_open_position_by_id(position_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Position {position_id} not found")
    storage.update_position(position_id, **updates)
    storage.audit("update.position", {"position_id": position_id, "fields": list(updates.keys())})
    return {"position_id": position_id, "updated": True, "fields": list(updates.keys())}


@app.put("/api/watchlist/{ticker}")
def update_watchlist(ticker: str, payload: dict):
    """Update watchlist entry (notes, is_favorite)."""
    allowed_fields = {"notes", "is_favorite"}
    updates = {k: v for k, v in payload.items() if k in allowed_fields}
    if not updates:
        raise HTTPException(status_code=400, detail=f"No valid fields. Allowed: {allowed_fields}")
    storage.update_watchlist(ticker, **updates)
    storage.audit("update.watchlist", {"ticker": ticker, "fields": list(updates.keys())})
    return {"ticker": ticker, "updated": True, "fields": list(updates.keys())}


@app.put("/api/system-state/{key}")
def set_system_state(key: str, payload: dict):
    """Set a system state key-value pair (e.g., circuit breaker flags)."""
    value = payload.get("value")
    if value is None:
        raise HTTPException(status_code=400, detail="Field 'value' is required")
    storage.set_state(key, str(value))
    storage.audit("set.system_state", {"key": key})
    return {"key": key, "set": True}


@app.get("/api/system-state/{key}")
def get_system_state(key: str):
    """Get a system state value by key."""
    value = storage.get_state(key)
    if value is None:
        raise HTTPException(status_code=404, detail=f"State key '{key}' not found")
    return {"key": key, "value": value}


# ====================== DELETE ENDPOINTS (CRUD completeness) ======================
@app.delete("/api/data/{ticker}")
def delete_ohlcv(ticker: str, timeframe: str = "1d"):
    """Delete all OHLCV data for a ticker."""
    deleted = storage.delete_ohlcv(ticker, timeframe=timeframe)
    storage.audit("delete.ohlcv", {"ticker": ticker, "timeframe": timeframe, "rows": deleted})
    return {"ticker": ticker, "deleted": deleted}


@app.delete("/api/scores/{ticker}")
def delete_scores(ticker: str, engine: str | None = None):
    """Delete scores for a ticker, optionally filtered by engine."""
    deleted = storage.delete_scores(ticker=ticker, engine=engine)
    storage.audit("delete.scores", {"ticker": ticker, "engine": engine, "rows": deleted})
    return {"ticker": ticker, "engine": engine, "deleted": deleted}


@app.delete("/api/orders")
def delete_orders(ticker: str | None = None, before_date: str | None = None):
    """Delete orders, optionally filtered by ticker and/or older than a date."""
    deleted = storage.delete_orders(ticker=ticker, before_date=before_date)
    storage.audit("delete.orders", {"ticker": ticker, "before_date": before_date, "rows": deleted})
    return {"deleted": deleted}


@app.delete("/api/audit")
def delete_audit_logs(before_date: str | None = None, event_type: str | None = None):
    """Delete audit logs, optionally filtered by date and/or event_type prefix."""
    deleted = storage.delete_audit_logs(before_date=before_date, event_type=event_type)
    return {"deleted": deleted}


@app.delete("/api/positions/{position_id}")
def delete_position(position_id: int):
    """Delete a position by ID."""
    deleted = storage.delete_position(position_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Position {position_id} not found")
    storage.audit("delete.position", {"position_id": position_id})
    return {"position_id": position_id, "deleted": True}


@app.delete("/api/ai/weights")
def delete_ai_weights(ticker: str | None = None, before_date: str | None = None):
    """Delete AI weight entries, optionally filtered by ticker and/or date."""
    deleted = storage.delete_ai_weights(ticker=ticker, before_date=before_date)
    storage.audit("delete.ai_weights", {"ticker": ticker, "before_date": before_date, "rows": deleted})
    return {"deleted": deleted}


@app.delete("/api/performance/snapshots")
def delete_equity_snapshots(before_date: str | None = None):
    """Delete equity snapshots, optionally older than a date."""
    deleted = storage.delete_equity_snapshots(before_date=before_date)
    storage.audit("delete.equity_snapshots", {"before_date": before_date, "rows": deleted})
    return {"deleted": deleted}


@app.delete("/api/risk/daily")
def delete_daily_risk_metrics(before_date: str | None = None):
    """Delete daily risk metrics, optionally older than a date."""
    deleted = storage.delete_daily_risk_metrics(before_date=before_date)
    storage.audit("delete.daily_risk", {"before_date": before_date, "rows": deleted})
    return {"deleted": deleted}


@app.delete("/api/archive/{ticker}")
def delete_archived_ticker(ticker: str):
    """Delete all Parquet files for a ticker from the archive."""
    from trading_system.data.archive import ArchiveAdapter
    adapter = ArchiveAdapter()
    deleted = adapter.delete_archived_ticker(ticker)
    storage.audit("delete.archive", {"ticker": ticker, "files": deleted})
    return {"ticker": ticker, "files_deleted": deleted}


@app.delete("/api/relationships")
def delete_relationships(asset_a: str | None = None):
    """Delete relationship matrix entries, optionally filtered by asset_a."""
    deleted = storage.delete_relationships(asset_a=asset_a)
    storage.audit("delete.relationships", {"asset_a": asset_a, "rows": deleted})
    return {"deleted": deleted}


@app.delete("/api/corporate-actions/{ticker}")
def delete_corporate_actions(ticker: str):
    """Delete corporate actions for a ticker."""
    deleted = storage.delete_corporate_actions(ticker)
    storage.audit("delete.corporate_actions", {"ticker": ticker, "rows": deleted})
    return {"ticker": ticker, "deleted": deleted}


@app.delete("/api/news")
def delete_news(source: str | None = None, before_date: str | None = None):
    """Delete news entries, optionally filtered by source and/or date."""
    deleted = storage.delete_news(source=source, before_date=before_date)
    storage.audit("delete.news", {"source": source, "before_date": before_date, "rows": deleted})
    return {"deleted": deleted}


# ====================== REPLAY SIMULATION ======================
@app.get("/api/replay/list")
def list_replay_results():
    """List all available replay result files."""
    import json as _json
    from pathlib import Path as _Path
    results_dir = _Path(__file__).resolve().parents[3] / "scripts" / "replay_results"
    if not results_dir.exists():
        return {"tickers": []}
    tickers = []
    for f in sorted(results_dir.glob("replay_*.json")):
        try:
            with open(f) as fh:
                data = _json.load(fh)
            tickers.append({
                "ticker": data.get("ticker", ""),
                "total_return_pct": data.get("total_return_pct", 0),
                "final_equity": data.get("final_equity", 0),
                "sharpe_ratio": data.get("sharpe_ratio", 0),
                "max_drawdown_pct": data.get("max_drawdown_pct", 0),
                "n_buys": data.get("n_buys", 0),
                "n_sells": data.get("n_sells", 0),
                "n_trading_days": data.get("n_trading_days", 0),
            })
        except Exception:
            pass
    return {"tickers": tickers}


@app.get("/api/replay/{ticker}")
def get_replay_result(ticker: str):
    """Get full replay result for a ticker, including day-by-day detail."""
    import json as _json
    import re
    from pathlib import Path as _Path
    # Sanitize ticker: keep only chars valid in IDX symbols (A-Z, 0-9, ., -).
    # This prevents path traversal (e.g. a ticker like "a/../../etc/passwd"
    # would otherwise escape the replay_results directory) and rejects any
    # path separators that Path would interpret as directory components.
    if not re.fullmatch(r"[A-Za-z0-9._-]+", ticker):
        raise HTTPException(status_code=400, detail="Invalid ticker format")
    ticker_safe = ticker.replace(".", "_")
    results_dir = _Path(__file__).resolve().parents[3] / "scripts" / "replay_results"
    result_file = results_dir / f"replay_{ticker_safe}.json"
    # Defense-in-depth: confirm the resolved path is still inside results_dir
    # (guards against any remaining traversal edge cases).
    try:
        result_file.resolve().relative_to(results_dir.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid ticker path") from exc
    if not result_file.exists():
        raise HTTPException(status_code=404, detail=f"No replay result for {ticker}")
    with open(result_file) as f:
        return _json.load(f)


# ====================== EXTENDED DATA (imported from MySQL) ======================
@app.get("/api/extended/snapshot/{ticker}")
def get_snapshot(ticker: str):
    """Get latest saham_snapshot (price + PER/PBV/ROE/DER/market_cap)."""
    from trading_system.data.extended_storage import ExtendedStorage
    ext = ExtendedStorage()
    kode = ticker.replace(".JK", "")
    result = ext.get_latest_snapshot(kode)
    if not result:
        raise HTTPException(status_code=404, detail=f"No snapshot for {ticker}")
    return result


@app.get("/api/extended/shareholders/{ticker}")
def get_shareholders(ticker: str):
    """Get shareholder data for a ticker."""
    from trading_system.data.extended_storage import ExtendedStorage
    ext = ExtendedStorage()
    kode = ticker.replace(".JK", "")
    df = ext.get_shareholders(kode)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No shareholders for {ticker}")
    return {"ticker": ticker, "shareholders": df.to_dict(orient="records"), "count": len(df)}


@app.get("/api/extended/directors/{ticker}")
def get_directors(ticker: str):
    """Get company directors for a ticker."""
    from trading_system.data.extended_storage import ExtendedStorage
    ext = ExtendedStorage()
    kode = ticker.replace(".JK", "")
    df = ext.get_directors(kode)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No directors for {ticker}")
    return {"ticker": ticker, "directors": df.to_dict(orient="records"), "count": len(df)}


@app.get("/api/extended/broker-summary")
def get_broker_summary_api(tanggal: str | None = None, limit: int = 50):
    """Get broker summary (top brokers by value)."""
    from trading_system.data.extended_storage import ExtendedStorage
    ext = ExtendedStorage()
    df = ext.get_broker_summary(tanggal=tanggal, limit=limit)
    return {"data": df.to_dict(orient="records"), "count": len(df)}


@app.get("/api/extended/pattern-reliability/{ticker}")
def get_pattern_reliability_api(ticker: str):
    """Get pattern reliability data for a ticker."""
    from trading_system.analysis.pattern_reliability import PatternReliabilityEngine
    engine = PatternReliabilityEngine()
    kode = ticker.replace(".JK", "")
    df = engine.get_reliable_patterns(kode=kode, min_win_rate=0, min_rating="average")
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No pattern reliability for {ticker}")
    return {"ticker": ticker, "patterns": df.to_dict(orient="records"), "count": len(df)}


@app.get("/api/extended/pattern-candidates")
def get_pattern_candidates_api(ticker: str | None = None):
    """Get pattern candidates (detected but not yet verified)."""
    from trading_system.data.extended_storage import ExtendedStorage
    ext = ExtendedStorage()
    kode = ticker.replace(".JK", "") if ticker else None
    df = ext.get_pattern_candidates(kode=kode, status="candidate")
    return {"data": df.to_dict(orient="records"), "count": len(df)}


@app.get("/api/extended/advanced-features/{ticker}")
def get_advanced_features_api(ticker: str):
    """Get advanced features (order flow, volume profile, anomalies) for a ticker."""
    from trading_system.data.extended_storage import ExtendedStorage
    ext = ExtendedStorage()
    kode = ticker.replace(".JK", "")
    result = ext.get_advanced_features_parsed(kode)
    if not result:
        raise HTTPException(status_code=404, detail=f"No advanced features for {ticker}")
    return result


@app.get("/api/extended/ai-scores-history/{ticker}")
def get_ai_scores_history_api(ticker: str, start: str | None = None, end: str | None = None):
    """Get historical AI scores with factor breakdown."""
    from trading_system.data.extended_storage import ExtendedStorage
    ext = ExtendedStorage()
    kode = ticker.replace(".JK", "")
    df = ext.get_ai_scores_history(kode=kode, start=start, end=end)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No AI scores history for {ticker}")
    return {"ticker": ticker, "history": df.to_dict(orient="records"), "count": len(df)}


@app.get("/api/extended/sentiment/{ticker}")
def get_idx_sentiment_api(ticker: str):
    """Get IDX historical sentiment data for a ticker."""
    from trading_system.data.extended_storage import ExtendedStorage
    ext = ExtendedStorage()
    symbol = ticker if ".JK" in ticker else f"{ticker}.JK"
    result = ext.get_latest_sentiment(symbol)
    if not result:
        raise HTTPException(status_code=404, detail=f"No sentiment data for {ticker}")
    return result


@app.get("/api/extended/market-indices")
def get_market_indices_api(index_name: str | None = None, start: str | None = None, end: str | None = None):
    """Get market index data (JCI, sectoral indices, etc.)."""
    from trading_system.data.extended_storage import ExtendedStorage
    ext = ExtendedStorage()
    df = ext.get_market_indices(index_name=index_name, start=start, end=end)
    if df.empty:
        raise HTTPException(status_code=404, detail="No market index data")
    return {"data": df.to_dict(orient="records"), "count": len(df)}


@app.get("/api/extended/financial-statements/{ticker}")
def get_financial_statements_api(ticker: str, period_type: str = "annual"):
    """Get financial statements for a ticker."""
    from trading_system.data.extended_storage import ExtendedStorage
    ext = ExtendedStorage()
    symbol = ticker if ".JK" in ticker else f"{ticker}.JK"
    df = ext.get_financial_statements(symbol=symbol, period_type=period_type)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No financial statements for {ticker}")
    return {"ticker": ticker, "statements": df.to_dict(orient="records"), "count": len(df)}


@app.get("/api/extended/social-media-sentiment/{ticker}")
def get_social_media_sentiment_api(ticker: str, platform: str | None = None, limit: int = 50):
    """Get social media sentiment posts for a ticker."""
    from trading_system.data.extended_storage import ExtendedStorage
    ext = ExtendedStorage()
    symbol = ticker if ".JK" in ticker else f"{ticker}.JK"
    df = ext.get_social_media_sentiment(symbol=symbol, platform=platform, limit=limit)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No social media sentiment for {ticker}")
    return {"ticker": ticker, "posts": df.to_dict(orient="records"), "count": len(df)}


@app.get("/api/extended/stock-splits/{ticker}")
def get_stock_splits_api(ticker: str):
    """Get stock split history for a ticker."""
    from trading_system.data.extended_storage import ExtendedStorage
    ext = ExtendedStorage()
    symbol = ticker if ".JK" in ticker else f"{ticker}.JK"
    df = ext.get_stock_splits(symbol=symbol)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No stock splits for {ticker}")
    return {"ticker": ticker, "splits": df.to_dict(orient="records"), "count": len(df)}


@app.get("/api/extended/quarterly-earnings/{ticker}")
def get_quarterly_earnings_api(ticker: str):
    """Get quarterly earnings data for a ticker."""
    from trading_system.data.extended_storage import ExtendedStorage
    ext = ExtendedStorage()
    symbol = ticker if ".JK" in ticker else f"{ticker}.JK"
    df = ext.get_quarterly_earnings(symbol=symbol)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No quarterly earnings for {ticker}")
    return {"ticker": ticker, "earnings": df.to_dict(orient="records"), "count": len(df)}


@app.get("/api/extended/circuit-breaker")
def get_circuit_breaker_status():
    """Get circuit breaker status."""
    from trading_system.risk.circuit_breaker import CircuitBreaker
    cb = CircuitBreaker()
    return cb.status()


if __name__ == "__main__":
    from trading_system.utils.logging_config import setup_logging
    setup_logging()
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
