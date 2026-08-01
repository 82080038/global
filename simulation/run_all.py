"""Main orchestrator — jalankan simulasi & testing seluruh fitur Trading System.

Penggunaan:
    # Jalankan semua modul
    python -m simulation.run_all

    # Jalankan modul tertentu saja
    python -m simulation.run_all --modules data,backtest,decision

    # Skip modul yang butuh API server
    python -m simulation.run_all --no-api

    # Pilih ticker
    python -m simulation.run_all --ticker TLKM.JK

Prasyarat:
    - Database SQLite sudah ada di data/trading_system.db
    - Untuk modul API: server API berjalan di localhost:8000
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from simulation.config import (
    API_BASE,
    API_KEY,
    DEFAULT_TICKERS,
    PRIMARY_TICKER,
    REPORT_DIR,
    SIM_BACKTEST_STRATEGIES,
    SIM_CAPITAL,
    SIM_MC_RUNS,
    SIM_WF_SPLITS,
    record,
    results,
)


# ═══════════════════════════════════════════════════════════════════════
# 1. DATA LAYER
# ═══════════════════════════════════════════════════════════════════════
def sim_data():
    """Test data layer: storage, validation, tickers."""
    from trading_system.data.storage import DataStorage
    from trading_system.data.validation import DataQualityValidator

    print("\n" + "=" * 60)
    print("  MODULE 1: DATA LAYER")
    print("=" * 60)

    storage = DataStorage()

    # List tickers
    try:
        tickers = storage.list_tickers()
        record("data", "list_tickers", "pass", f"{len(tickers)} tickers in DB", {"tickers": tickers[:20]})
    except Exception as e:
        record("data", "list_tickers", "fail", str(e))
        return

    # Load OHLCV for primary ticker
    try:
        df = storage.load_ohlcv(PRIMARY_TICKER)
        if df.empty:
            record("data", "load_ohlcv", "warn", f"No OHLCV data for {PRIMARY_TICKER}")
        else:
            record("data", "load_ohlcv", "pass",
                   f"{len(df)} rows for {PRIMARY_TICKER}",
                   {"columns": list(df.columns), "date_range": f"{df.index[0]} → {df.index[-1]}"})
    except Exception as e:
        record("data", "load_ohlcv", "fail", str(e))

    # Validation
    try:
        validator = DataQualityValidator()
        if not df.empty:
            clean, report = validator.validate(df)
            record("data", "validation", "pass",
                   f"quality={report.data_quality_score} tier={report.tier} action={report.action}")
        else:
            record("data", "validation", "skip", "No data to validate")
    except Exception as e:
        record("data", "validation", "fail", str(e))

    # Watchlist
    try:
        watchlist = storage.get_watchlist(favorites_only=False)
        record("data", "watchlist", "pass", f"{len(watchlist)} items", {"items": watchlist[:5]})
    except Exception as e:
        record("data", "watchlist", "fail", str(e))


# ═══════════════════════════════════════════════════════════════════════
# 2. ANALYSIS PIPELINE
# ═══════════════════════════════════════════════════════════════════════
def sim_analysis():
    """Test analysis pipeline: technical, fundamental, macro, global, relationship, sentiment."""
    from trading_system.analysis.pipeline import AnalysisPipeline

    print("\n" + "=" * 60)
    print("  MODULE 2: ANALYSIS PIPELINE")
    print("=" * 60)

    pipeline = AnalysisPipeline()

    try:
        result = pipeline.compute(PRIMARY_TICKER, period="1y")
        if result["status"] == "error":
            record("analysis", "pipeline_compute", "fail", result["message"])
        else:
            scores = result.get("scores", {})
            record("analysis", "pipeline_compute", "pass",
                   f"{len(scores)} scores computed",
                   {"scores": scores, "as_of": result.get("as_of")})
    except Exception as e:
        record("analysis", "pipeline_compute", "fail", str(e))

    # Technical indicators
    try:
        from trading_system.analysis.technical import TechnicalAnalysisEngine
        from trading_system.data.storage import DataStorage

        df = DataStorage().load_ohlcv(PRIMARY_TICKER)
        if not df.empty:
            engine = TechnicalAnalysisEngine()
            engine.ohlcv = df
            df_ind = engine.compute_indicators()
            indicator_cols = [c for c in df_ind.columns if c in ("rsi", "macd", "macd_signal", "ma_20", "ma_50", "bb_upper", "bb_lower")]
            record("analysis", "technical_indicators", "pass",
                   f"{len(indicator_cols)} indicators: {indicator_cols}")
        else:
            record("analysis", "technical_indicators", "skip", "No data")
    except Exception as e:
        record("analysis", "technical_indicators", "fail", str(e))

    # Relationship
    try:
        from trading_system.analysis.relationship import MarketRelationshipEngine

        rel = MarketRelationshipEngine(window=60)
        result = rel.compute(PRIMARY_TICKER)
        if result.get("status") == "error":
            record("analysis", "relationship", "warn", result.get("message", "error"))
        else:
            relationships = result.get("relationships", [])
            record("analysis", "relationship", "pass",
                   f"score={result.get('score')}, {len(relationships)} relationships")
    except Exception as e:
        record("analysis", "relationship", "fail", str(e))


# ═══════════════════════════════════════════════════════════════════════
# 3. DECISION ENGINE
# ═══════════════════════════════════════════════════════════════════════
def sim_decision():
    """Test decision engine: recommendation, conviction, position sizing."""
    from trading_system.decision.engine import DecisionEngine

    print("\n" + "=" * 60)
    print("  MODULE 3: DECISION ENGINE")
    print("=" * 60)

    engine = DecisionEngine()

    for ticker in DEFAULT_TICKERS[:3]:
        try:
            result = engine.recommend(ticker, capital=SIM_CAPITAL)
            if result["status"] == "error":
                record("decision", f"recommend_{ticker}", "warn", result["message"])
            else:
                rec = result["recommendation"]
                record("decision", f"recommend_{ticker}", "pass",
                       f"action={rec['action']} conviction={rec['conviction_score']}",
                       {"action": rec["action"], "conviction": rec["conviction_score"],
                        "position_size": rec["position_size"], "entry": rec["entry_price_range"],
                        "stop_loss": rec["stop_loss"], "take_profit": rec["take_profit"]})
        except Exception as e:
            record("decision", f"recommend_{ticker}", "fail", str(e))


# ═══════════════════════════════════════════════════════════════════════
# 4. RISK MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════
def sim_risk():
    """Test risk engine: VaR, CVaR, position sizing, Kelly."""
    from trading_system.risk.engine import RiskEngine

    print("\n" + "=" * 60)
    print("  MODULE 4: RISK MANAGEMENT")
    print("=" * 60)

    engine = RiskEngine()

    try:
        result = engine.analyze(PRIMARY_TICKER, capital=SIM_CAPITAL)
        if result.get("status") == "error":
            record("risk", "analyze", "warn", result.get("message", "error"))
        else:
            record("risk", "analyze", "pass",
                   f"VaR={result.get('var_95', 'N/A')} CVaR={result.get('cvar_95', 'N/A')}",
                   {"var_95": result.get("var_95"), "cvar_95": result.get("cvar_95"),
                    "position_size": result.get("position_size"), "risk_flags": result.get("risk_flags", [])})
    except Exception as e:
        record("risk", "analyze", "fail", str(e))

    # Costs
    try:
        from trading_system.risk.costs import CostModel

        calc = CostModel()
        fees = calc.compute_fees(order_value=10_000_000, action="buy")
        record("risk", "transaction_costs", "pass",
               f"Rp 10M buy fees: Rp {fees['total']:,.0f} (brokerage={fees['brokerage']} levy={fees['levy']} tax={fees['tax']})",
               {"fees": fees, "buy_cost_pct": calc.buy_cost_pct()})
    except Exception as e:
        record("risk", "transaction_costs", "fail", str(e))


# ═══════════════════════════════════════════════════════════════════════
# 5. BACKTEST
# ═══════════════════════════════════════════════════════════════════════
def sim_backtest():
    """Test backtest engine: multiple strategies, Monte Carlo, Walk-Forward."""
    from trading_system.backtest.engine import BacktestEngine
    from trading_system.backtest.strategies import BuyAndHold, ConvictionStrategy, MovingAverageCrossover

    print("\n" + "=" * 60)
    print("  MODULE 5: BACKTEST")
    print("=" * 60)

    engine = BacktestEngine()

    for strategy_name in SIM_BACKTEST_STRATEGIES:
        try:
            if strategy_name == "buy_and_hold":
                strategy = BuyAndHold()
            elif strategy_name == "ma_crossover":
                strategy = MovingAverageCrossover()
            elif strategy_name == "conviction":
                strategy = ConvictionStrategy(storage=engine.storage, ticker=PRIMARY_TICKER)
            else:
                continue

            result = engine.run(PRIMARY_TICKER, strategy, initial_capital=SIM_CAPITAL)
            if result.get("status") != "ok":
                record("backtest", strategy_name, "warn", result.get("message", "error"))
                continue

            m = result.get("metrics", {})
            record("backtest", strategy_name, "pass",
                   f"return={m.get('total_return', 0)*100:.2f}% sharpe={m.get('sharpe_ratio', 0):.4f} "
                   f"maxDD={m.get('max_drawdown', 0)*100:.2f}% trades={m.get('number_of_trades', 0)}",
                   {"final_equity": result["final_equity"], "metrics": m})
        except Exception as e:
            record("backtest", strategy_name, "fail", str(e))

    # Monte Carlo
    try:
        from trading_system.backtest.metrics import monte_carlo_simulation

        df = engine.storage.load_ohlcv(PRIMARY_TICKER)
        if not df.empty:
            returns = df["close"].pct_change().dropna()
            mc = monte_carlo_simulation(returns, n_simulations=SIM_MC_RUNS, initial_capital=SIM_CAPITAL)
            if mc.get("status") != "insufficient_data":
                record("backtest", "monte_carlo", "pass",
                       f"{SIM_MC_RUNS} runs | prob_profit={mc['prob_profit']*100:.1f}% "
                       f"worst_DD={mc['worst_drawdown']*100:.2f}%",
                       {"mean_final": mc["mean_final_equity"], "p5": mc["final_equity"]["p5"],
                        "p95": mc["final_equity"]["p95"]})
            else:
                record("backtest", "monte_carlo", "skip", "Insufficient data")
        else:
            record("backtest", "monte_carlo", "skip", "No data")
    except Exception as e:
        record("backtest", "monte_carlo", "fail", str(e))

    # Walk-Forward
    try:
        from trading_system.backtest.metrics import walk_forward_analysis

        if not df.empty:
            wf = walk_forward_analysis(df, lambda: MovingAverageCrossover(), n_splits=SIM_WF_SPLITS)
            if wf.get("status") not in ("insufficient_data", "no_valid_splits"):
                record("backtest", "walk_forward", "pass",
                       f"OOS mean return={wf['oos_mean_return']*100:.2f}% "
                       f"consistency={wf['oos_consistency']*100:.1f}%",
                       {"splits": len(wf["splits"]), "oos_mean_sharpe": wf["oos_mean_sharpe"]})
            else:
                record("backtest", "walk_forward", "skip", f"Status: {wf.get('status')}")
        else:
            record("backtest", "walk_forward", "skip", "No data")
    except Exception as e:
        record("backtest", "walk_forward", "fail", str(e))


# ═══════════════════════════════════════════════════════════════════════
# 6. PAPER TRADING
# ═══════════════════════════════════════════════════════════════════════
def sim_paper_trading():
    """Test paper trading simulator."""
    from trading_system.paper_trading.engine import PaperTradingEngine

    print("\n" + "=" * 60)
    print("  MODULE 6: PAPER TRADING")
    print("=" * 60)

    try:
        engine = PaperTradingEngine(cash=SIM_CAPITAL)
        result = engine.simulate(PRIMARY_TICKER)
        if result.get("status") == "error":
            record("paper_trading", "simulate", "warn", result.get("message", "error"))
        else:
            record("paper_trading", "simulate", "pass",
                   f"final_equity={result.get('final_equity', 'N/A')} "
                   f"trades={result.get('trades', 'N/A')}",
                   {"result": result})
    except Exception as e:
        record("paper_trading", "simulate", "fail", str(e))


# ═══════════════════════════════════════════════════════════════════════
# 7. EXECUTION
# ═══════════════════════════════════════════════════════════════════════
def sim_execution():
    """Test execution engine: broker adapter, automated execution."""
    from trading_system.execution.broker_adapter import MockBrokerAdapter

    print("\n" + "=" * 60)
    print("  MODULE 7: EXECUTION")
    print("=" * 60)

    # Mock broker adapter
    try:
        from trading_system.execution.broker_adapter import BrokerOrder

        adapter = MockBrokerAdapter()
        order = BrokerOrder(
            ticker=PRIMARY_TICKER,
            action="buy",
            shares=100,
            price=8000,
            order_type="limit",
        )
        result = adapter.place_order(order)
        record("execution", "mock_broker_place_order", "pass",
               f"status={result.status} filled_price={result.filled_price} fees={result.fees}",
               {"result": result.__dict__})
    except Exception as e:
        record("execution", "mock_broker_place_order", "fail", str(e))

    # Automated execution (one cycle)
    try:
        from trading_system.execution.automated import AutomatedExecutionEngine

        engine = AutomatedExecutionEngine()
        results_list = engine.run_once([PRIMARY_TICKER])
        record("execution", "automated_run_once", "pass",
               f"{len(results_list)} results", {"results": results_list[:3]})
    except Exception as e:
        record("execution", "automated_run_once", "fail", str(e))


# ═══════════════════════════════════════════════════════════════════════
# 8. PORTFOLIO
# ═══════════════════════════════════════════════════════════════════════
def sim_portfolio():
    """Test portfolio: performance analytics, rebalancer."""
    print("\n" + "=" * 60)
    print("  MODULE 8: PORTFOLIO")
    print("=" * 60)

    # Performance
    try:
        from trading_system.portfolio.performance import PerformanceAnalytics
        from trading_system.data.storage import DataStorage

        analytics = PerformanceAnalytics(storage=DataStorage())
        perf = analytics.get_performance(period="1M")
        record("portfolio", "performance_1M", "pass",
               f"equity={perf.get('equity', 'N/A')} return={perf.get('return_pct', 'N/A')}%",
               {"perf": perf})
    except Exception as e:
        record("portfolio", "performance_1M", "fail", str(e))

    # Rebalancer status
    try:
        from trading_system.portfolio.rebalancer import PortfolioRebalancer
        from trading_system.data.storage import DataStorage

        rebalancer = PortfolioRebalancer(storage=DataStorage())
        status = rebalancer.get_rebalance_status()
        record("portfolio", "rebalancer_status", "pass",
               f"enabled={status.get('rebalance_enabled')} drift={status.get('max_drift', 'N/A')}",
               {"status": status})
    except Exception as e:
        record("portfolio", "rebalancer_status", "fail", str(e))


# ═══════════════════════════════════════════════════════════════════════
# 9. AI LEARNING
# ═══════════════════════════════════════════════════════════════════════
def sim_ai_learning():
    """Test AI learning: weight optimization, model registry."""
    from trading_system.ai_learning.engine import AILearningEngine

    print("\n" + "=" * 60)
    print("  MODULE 9: AI LEARNING")
    print("=" * 60)

    try:
        engine = AILearningEngine()
        result = engine.train_linear_regression(ticker=PRIMARY_TICKER)
        if result.get("status") == "error":
            record("ai_learning", "train_lr", "warn", result.get("message", "error"))
        else:
            record("ai_learning", "train_lr", "pass",
                   f"r2={result.get('r2_score', 'N/A')} weights={result.get('weights', {})}",
                   {"result": result})
    except Exception as e:
        record("ai_learning", "train_lr", "fail", str(e))

    # Get weights
    try:
        weights = engine.storage.get_ai_weights(ticker=PRIMARY_TICKER, max_age_days=365)
        if weights:
            record("ai_learning", "get_weights", "pass", f"weights={weights}")
        else:
            record("ai_learning", "get_weights", "warn", "No trained weights found")
    except Exception as e:
        record("ai_learning", "get_weights", "fail", str(e))


# ═══════════════════════════════════════════════════════════════════════
# 10. XAI (Explainable AI)
# ═══════════════════════════════════════════════════════════════════════
def sim_xai():
    """Test XAI engine: narrative explanation, top factors."""
    from trading_system.decision.engine import DecisionEngine
    from trading_system.xai.engine import ExplainableAIEngine

    print("\n" + "=" * 60)
    print("  MODULE 10: XAI (EXPLAINABLE AI)")
    print("=" * 60)

    try:
        dec = DecisionEngine().recommend(PRIMARY_TICKER)
        if dec["status"] == "error":
            record("xai", "explain", "warn", f"Decision failed: {dec['message']}")
            return

        xai = ExplainableAIEngine()
        explanation = xai.explain(PRIMARY_TICKER, dec["recommendation"])
        narrative = explanation.get("narrative", "")
        top_factors = explanation.get("top_factors", [])
        record("xai", "explain", "pass",
               f"narrative_len={len(narrative)} top_factors={len(top_factors)}",
               {"narrative": narrative[:300], "top_factors": top_factors})
    except Exception as e:
        record("xai", "explain", "fail", str(e))


# ═══════════════════════════════════════════════════════════════════════
# 11. MONITORING
# ═══════════════════════════════════════════════════════════════════════
def sim_monitoring():
    """Test monitoring engine: system health check."""
    from trading_system.monitoring.engine import MonitoringEngine

    print("\n" + "=" * 60)
    print("  MODULE 11: MONITORING")
    print("=" * 60)

    try:
        engine = MonitoringEngine()
        health = engine.health()
        record("monitoring", "health_check", "pass",
               f"status={health.get('status', 'N/A')} tickers={len(health.get('tickers_in_db', []))}",
               {"health": health})
    except Exception as e:
        record("monitoring", "health_check", "fail", str(e))


# ═══════════════════════════════════════════════════════════════════════
# 12. CORPORATE ACTIONS
# ═══════════════════════════════════════════════════════════════════════
def sim_corporate():
    """Test corporate actions engine."""
    from trading_system.corporate.actions import CorporateActionEngine

    print("\n" + "=" * 60)
    print("  MODULE 12: CORPORATE ACTIONS")
    print("=" * 60)

    try:
        engine = CorporateActionEngine()
        result = engine.fetch(PRIMARY_TICKER)
        if result.get("status") == "error":
            record("corporate", "fetch_actions", "warn", result.get("message", "error"))
        else:
            actions = result.get("actions", [])
            record("corporate", "fetch_actions", "pass",
                   f"{len(actions)} actions for {PRIMARY_TICKER}",
                   {"actions": actions[:5]})
    except Exception as e:
        record("corporate", "fetch_actions", "fail", str(e))


# ═══════════════════════════════════════════════════════════════════════
# 13. SENTIMENT
# ═══════════════════════════════════════════════════════════════════════
def sim_sentiment():
    """Test sentiment engine."""
    print("\n" + "=" * 60)
    print("  MODULE 13: SENTIMENT")
    print("=" * 60)

    try:
        from trading_system.sentiment.engine import SentimentEngine

        engine = SentimentEngine()
        result = engine.compute(PRIMARY_TICKER)
        record("sentiment", "compute", "pass",
               f"score={result.get('score', 'N/A')} label={result.get('label', 'N/A')}",
               {"result": result})
    except Exception as e:
        record("sentiment", "compute", "fail", str(e))


# ═══════════════════════════════════════════════════════════════════════
# 14. API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════
def sim_api():
    """Test all API endpoints via HTTP."""
    import urllib.request

    print("\n" + "=" * 60)
    print("  MODULE 14: API ENDPOINTS")
    print("=" * 60)

    endpoints = [
        ("GET", "/api/health"),
        ("GET", "/api/monitor"),
        ("GET", "/api/tickers"),
        ("GET", "/api/watchlist"),
        ("GET", "/api/watchlist/all"),
        ("GET", "/api/performance?period=1M"),
        ("GET", "/api/engines"),
        ("GET", f"/api/data/ohlcv?ticker={PRIMARY_TICKER}&limit=5"),
        ("GET", f"/api/indicators/{PRIMARY_TICKER}"),
        ("GET", f"/api/scores/{PRIMARY_TICKER}"),
        ("GET", f"/api/recommend/{PRIMARY_TICKER}"),
        ("GET", f"/api/explain/{PRIMARY_TICKER}"),
        ("GET", f"/api/risk/{PRIMARY_TICKER}"),
        ("GET", f"/api/corporate/{PRIMARY_TICKER}"),
        ("GET", f"/api/relationship/{PRIMARY_TICKER}"),
        ("GET", f"/api/factor-weights/{PRIMARY_TICKER}"),
        ("GET", f"/api/sentiment/{PRIMARY_TICKER}"),
        ("GET", "/api/positions"),
        ("GET", "/api/orders?limit=10"),
        ("GET", "/api/portfolio/exposure"),
        ("GET", "/api/execution/toggle"),
        ("GET", "/api/rebalance/toggle"),
        ("GET", "/api/rebalance/status"),
        ("GET", "/api/execution/logs?limit=10"),
        ("GET", "/api/audit?limit=10"),
        ("GET", "/api/risk/daily?limit=10"),
        ("GET", "/api/ai/weights"),
        ("GET", "/api/replay/list"),
    ]

    for method, ep in endpoints:
        try:
            url = f"{API_BASE}{ep}"
            req = urllib.request.Request(url, method=method)
            req.add_header("X-API-Key", API_KEY)
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
                status_code = resp.status
                data_len = len(body)
                record("api", ep.split("?")[0], "pass",
                       f"HTTP {status_code} ({data_len} bytes)")
        except urllib.error.HTTPError as e:
            record("api", ep.split("?")[0], "warn", f"HTTP {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            record("api", ep.split("?")[0], "fail", f"Connection error: {e.reason}")
        except Exception as e:
            record("api", ep.split("?")[0], "fail", str(e))


# ═══════════════════════════════════════════════════════════════════════
# 15. CLI
# ═══════════════════════════════════════════════════════════════════════
def sim_cli():
    """Test CLI commands via subprocess."""
    import subprocess

    print("\n" + "=" * 60)
    print("  MODULE 15: CLI COMMANDS")
    print("=" * 60)

    commands = [
        ("list", [sys.executable, "-m", "trading_system.cli", "list"]),
        ("monitor", [sys.executable, "-m", "trading_system.cli", "monitor"]),
        ("recommend", [sys.executable, "-m", "trading_system.cli", "recommend", PRIMARY_TICKER]),
        ("explain", [sys.executable, "-m", "trading_system.cli", "explain", PRIMARY_TICKER]),
    ]

    for name, cmd in commands:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=str(Path(__file__).resolve().parents[1]))
            if proc.returncode == 0:
                output_preview = proc.stdout[:200].replace("\n", " | ")
                record("cli", name, "pass", f"exit=0 output={output_preview}")
            else:
                record("cli", name, "warn", f"exit={proc.returncode} stderr={proc.stderr[:200]}")
        except subprocess.TimeoutExpired:
            record("cli", name, "warn", "Timeout (60s)")
        except Exception as e:
            record("cli", name, "fail", str(e))


# ═══════════════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════

MODULE_MAP = {
    "data": sim_data,
    "analysis": sim_analysis,
    "decision": sim_decision,
    "risk": sim_risk,
    "backtest": sim_backtest,
    "paper_trading": sim_paper_trading,
    "execution": sim_execution,
    "portfolio": sim_portfolio,
    "ai_learning": sim_ai_learning,
    "xai": sim_xai,
    "monitoring": sim_monitoring,
    "corporate": sim_corporate,
    "sentiment": sim_sentiment,
    "api": sim_api,
    "cli": sim_cli,
}


def main():
    parser = argparse.ArgumentParser(description="Trading System — Full Feature Simulation & Testing")
    parser.add_argument("--modules", default=None, help=f"Comma-separated module names: {','.join(MODULE_MAP.keys())}")
    parser.add_argument("--no-api", action="store_true", help="Skip API endpoint tests")
    parser.add_argument("--no-cli", action="store_true", help="Skip CLI tests")
    parser.add_argument("--ticker", default=None, help="Override primary ticker")
    args = parser.parse_args()

    if args.ticker:
        import simulation.config as cfg

        cfg.PRIMARY_TICKER = args.ticker
        global PRIMARY_TICKER
        PRIMARY_TICKER = args.ticker

    if args.modules:
        modules_to_run = args.modules.split(",")
    else:
        modules_to_run = list(MODULE_MAP.keys())

    if args.no_api:
        modules_to_run = [m for m in modules_to_run if m != "api"]
    if args.no_cli:
        modules_to_run = [m for m in modules_to_run if m != "cli"]

    print("=" * 60)
    print("  TRADING SYSTEM — FULL FEATURE SIMULATION & TESTING")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Primary Ticker: {PRIMARY_TICKER}")
    print(f"  Capital: Rp {SIM_CAPITAL:,}")
    print(f"  Modules: {', '.join(modules_to_run)}")
    print("=" * 60)

    t0 = time.time()

    for mod_name in modules_to_run:
        func = MODULE_MAP.get(mod_name)
        if not func:
            print(f"\n  [SKIP] Unknown module: {mod_name}")
            continue
        try:
            func()
        except Exception as e:
            record(mod_name, "_module_crash", "fail", str(e))
            traceback.print_exc()

    elapsed = time.time() - t0

    # Summary
    print("\n" + "=" * 60)
    print("  SIMULATION SUMMARY")
    print("=" * 60)

    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    warned = sum(1 for r in results if r["status"] == "warn")
    skipped = sum(1 for r in results if r["status"] == "skip")

    # Group by module
    modules_seen = {}
    for r in results:
        mod = r["module"]
        if mod not in modules_seen:
            modules_seen[mod] = {"pass": 0, "fail": 0, "warn": 0, "skip": 0}
        modules_seen[mod][r["status"]] = modules_seen[mod].get(r["status"], 0) + 1

    for mod, counts in modules_seen.items():
        total = sum(counts.values())
        print(f"  {mod:20s} | {total:3d} tests | pass={counts['pass']} fail={counts['fail']} warn={counts['warn']} skip={counts.get('skip', 0)}")

    print(f"\n  Total: {len(results)} | Pass: {passed} | Fail: {failed} | Warn: {warned} | Skip: {skipped}")
    print(f"  Elapsed: {elapsed:.1f}s")

    # Save JSON report
    report_path = REPORT_DIR / f"sim_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_data = {
        "timestamp": datetime.now().isoformat(),
        "elapsed_seconds": round(elapsed, 2),
        "primary_ticker": PRIMARY_TICKER,
        "capital": SIM_CAPITAL,
        "summary": {
            "total": len(results),
            "pass": passed,
            "fail": failed,
            "warn": warned,
            "skip": skipped,
        },
        "modules": modules_seen,
        "results": results,
    }
    with open(report_path, "w") as f:
        json.dump(report_data, f, indent=2, default=str)
    print(f"\n  Report: {report_path}")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
