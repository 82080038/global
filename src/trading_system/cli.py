"""CLI untuk Phase 1: fetch data, validate, backtest."""

import argparse
import sys
from pathlib import Path

# Add src to path when running as script
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from trading_system.analysis.pipeline import AnalysisPipeline
from trading_system.backtest.engine import BacktestEngine
from trading_system.backtest.strategies import BuyAndHold, MovingAverageCrossover
from trading_system.config import TRADING_CAPITAL
from trading_system.corporate.actions import CorporateActionEngine
from trading_system.data.acquisition import YahooFinanceAdapter, normalize_ohlcv
from trading_system.data.storage import DataStorage
from trading_system.data.validation import DataQualityValidator
from trading_system.decision.engine import DecisionEngine
from trading_system.analysis.relationship import MarketRelationshipEngine
from trading_system.monitoring.engine import MonitoringEngine
from trading_system.paper_trading.engine import PaperTradingEngine
from trading_system.xai.engine import ExplainableAIEngine


def fetch_and_store(tickers, period="2y"):
    adapter = YahooFinanceAdapter()
    storage = DataStorage()
    validator = DataQualityValidator()
    for t in tickers:
        print(f"Fetching {t}...")
        result = adapter.fetch(t, period=period)
        if result["status"] == "ok":
            raw = normalize_ohlcv(result["records"])
            clean, report = validator.validate(raw)
            if report.action == "pause":
                print(f"  FAILED quality ({report.data_quality_score}, tier={report.tier}): {report.anomalies}")
                continue
            elif report.action == "delayed_review":
                print(f"  DELAYED ({report.data_quality_score}, tier={report.tier}): queued for review. Anomalies: {report.anomalies}")
            n = storage.save_ohlcv(clean)
            print(f"  Saved {n} rows for {t}. Quality={report.data_quality_score} tier={report.tier}")
        else:
            print(f"  Error: {result['message']}")


def list_tickers():
    s = DataStorage()
    equity = s.list_active_equity_tickers()
    all_tickers = s.list_tickers()
    non_equity = [t for t in all_tickers if t not in equity]
    print(f"\nTotal tickers in OHLCV: {len(all_tickers)}")
    print(f"  Active equity (saham listed): {len(equity)}")
    print(f"  Non-equity (forex/index/commodity/ETF): {len(non_equity)}")
    print(f"\nEquity tickers: {equity[:20]}{'...' if len(equity) > 20 else ''}")
    if non_equity:
        print(f"Non-equity tickers: {non_equity}")


def recommend(ticker: str, capital: float = TRADING_CAPITAL):
    engine = DecisionEngine()
    result = engine.recommend(ticker, capital=capital)
    if result["status"] == "error":
        print(f"Error: {result['message']}")
        return
    rec = result["recommendation"]
    print(f"\nRecommendation for {ticker}")
    print(f"  Action: {rec['action']}")
    print(f"  Conviction: {rec['conviction_score']}")
    print(f"  Position Size: {rec['position_size']}")
    print(f"  Entry: {rec['entry_price_range']}")
    print(f"  Stop Loss: {rec['stop_loss']}")
    print(f"  Take Profit: {rec['take_profit']}")
    print(f"  Risk Flags: {rec['risk_flags']}")
    print(f"  Contributing Scores: {rec['contributing_scores']}")


def compute_scores(ticker: str, period: str = "2y"):
    pipeline = AnalysisPipeline()
    result = pipeline.compute(ticker, period)
    if result["status"] == "error":
        print(f"Error: {result['message']}")
        return
    print(f"\nScores for {ticker} (as_of {result['as_of']})")
    for engine, score in result["scores"].items():
        print(f"  {engine}: {score}")
    for engine, detail in result["details"].items():
        if isinstance(detail, dict):
            breakdown = detail.get("breakdown") or detail.get("regime") or detail.get("ratios") or detail.get("relationships")
            if breakdown:
                print(f"    {engine} detail: {breakdown}")


def main():
    parser = argparse.ArgumentParser(description="Trading System CLI")
    sub = parser.add_subparsers(dest="cmd")

    p_fetch = sub.add_parser("fetch", help="Fetch and validate OHLCV")
    p_fetch.add_argument("tickers", nargs="*", default=None, help="List of tickers (use .JK suffix for IDX)")
    p_fetch.add_argument("--period", default="2y", help="Yahoo Finance period")
    p_fetch.add_argument("--all", action="store_true", help="Fetch all active equity tickers")

    p_backtest = sub.add_parser("backtest", help="Run backtest")
    p_backtest.add_argument("ticker", help="Ticker to backtest")
    p_backtest.add_argument("--strategy", default="buy_and_hold", help="buy_and_hold, ma_crossover, or conviction")
    p_backtest.add_argument("--capital", type=float, default=TRADING_CAPITAL)
    p_backtest.add_argument("--monte-carlo", action="store_true", help="Run Monte Carlo simulation")
    p_backtest.add_argument("--walk-forward", action="store_true", help="Run walk-forward analysis")
    p_backtest.add_argument("--n-simulations", type=int, default=1000, help="Number of MC simulations")
    p_backtest.add_argument("--n-splits", type=int, default=5, help="Number of WF splits")
    p_backtest.add_argument("--block-size", type=int, default=None, help="Block size for block-bootstrap MC (None=IID)")

    p_idx_foreign = sub.add_parser("fetch-idx-foreign-flow", help="Batch scrape real foreign flow from idx.co.id")
    p_idx_foreign.add_argument("--start", default="2020-01-02", help="Start date YYYY-MM-DD")
    p_idx_foreign.add_argument("--end", default=None, help="End date YYYY-MM-DD")
    p_idx_foreign.add_argument("--tickers", nargs="*", default=None, help="Stock codes to filter (default: 47 blue chips)")
    p_idx_foreign.add_argument("--delay", type=float, default=0.3, help="Delay between requests in seconds")

    p_idx_broker = sub.add_parser("fetch-idx-broker-flow", help="Batch scrape broker summary from idx.co.id")
    p_idx_broker.add_argument("--start", default="2020-01-02", help="Start date YYYY-MM-DD")
    p_idx_broker.add_argument("--end", default=None, help="End date YYYY-MM-DD")
    p_idx_broker.add_argument("--delay", type=float, default=0.3, help="Delay between requests in seconds")

    p_list = sub.add_parser("list", help="List tickers in DB")

    p_scores = sub.add_parser("compute-scores", help="Compute technical/fundamental/macro/global/relationship/sentiment scores")
    p_scores.add_argument("ticker", nargs="?", default=None, help="Ticker to analyze (or use --all)")
    p_scores.add_argument("--period", default="2y", help="Data period for OHLCV")
    p_scores.add_argument("--all", action="store_true", help="Compute scores for all active equity tickers")

    p_corp = sub.add_parser("corporate-actions", help="Fetch and list corporate actions")
    p_corp.add_argument("ticker", help="Ticker")

    p_adj = sub.add_parser("update-adjusted-close", help="Recompute adjusted_close from corporate actions")
    p_adj.add_argument("ticker", help="Ticker")

    p_imp = sub.add_parser("import-legacy", help="Import data from legacy saham.db")
    p_imp.add_argument("--source", default="C:/xampp/htdocs/pasar_modal/data/saham.db", help="Source SQLite DB path")

    p_rel = sub.add_parser("relationship", help="Compute rolling correlation with global/macro assets")
    p_rel.add_argument("ticker", help="Ticker")
    p_rel.add_argument("--window", type=int, default=60, help="Rolling window")

    p_rec = sub.add_parser("recommend", help="Generate BUY/HOLD/SELL recommendation")
    p_rec.add_argument("ticker", help="Ticker")
    p_rec.add_argument("--capital", type=float, default=TRADING_CAPITAL)

    p_exp = sub.add_parser("explain", help="Explain recommendation for a ticker")
    p_exp.add_argument("ticker", help="Ticker")

    p_mon = sub.add_parser("monitor", help="System health check")

    p_paper = sub.add_parser("paper-trade", help="Simulate paper trade")
    p_paper.add_argument("ticker", help="Ticker")
    p_paper.add_argument("--capital", type=float, default=TRADING_CAPITAL)

    p_exec = sub.add_parser("execution", help="Run automated execution engine (robot trader)")
    p_exec.add_argument("--once", action="store_true", help="Run one cycle and exit")
    p_exec.add_argument("--interval", type=int, default=15, help="Check interval in minutes")
    p_exec.add_argument("--tickers", nargs="*", help="Specific tickers to process")

    p_e2e = sub.add_parser("test-e2e", help="Run end-to-end pipeline test")
    p_e2e.add_argument("--tickers", nargs="+", default=["BBCA.JK", "TLKM.JK", "ASII.JK"], help="Tickers to test")

    p_sched = sub.add_parser("schedule", help="Run daily scheduler (fetch, scores, recommendations, execution)")
    p_sched.add_argument("--once", action="store_true", help="Run daily job once and exit")

    p_status = sub.add_parser("data-status", help="Show data freshness — last fetched date per ticker")
    p_status.add_argument("--limit", type=int, default=20, help="Number of tickers to show (default: 20)")
    p_status.add_argument("--stale-only", action="store_true", help="Only show tickers with stale data")
    p_status.add_argument("--table", default="ohlcv", help="Table name to check (default: ohlcv)")

    p_catchup = sub.add_parser("catch-up", help="Fetch all stale tickers to fill data gaps")
    p_catchup.add_argument("--tickers", nargs="*", help="Specific tickers (default: all stale)")
    p_catchup.add_argument("--max-days", type=int, default=1, help="Max days behind to consider stale (default: 1)")
    p_catchup.add_argument("--period", default="2y", help="Yahoo Finance period for full fetch (default: 2y)")

    p_screen = sub.add_parser("screen", help="Screen & rank universe of stocks for trading candidates")
    p_screen.add_argument("--mode", choices=["technical", "factors"], default="factors",
                          help="Screener mode: 'factors' (FactorEngine composite rank) or 'technical' (template-based)")
    p_screen.add_argument("--template", choices=["technical", "momentum", "value"], default="technical",
                          help="Template for technical mode (default: technical)")
    p_screen.add_argument("--top", type=int, default=20, help="Number of top-ranked results to show")
    p_screen.add_argument("--tickers", nargs="*", help="Restrict universe (default: all IDX .JK tickers)")
    p_screen.add_argument("--max-tickers", type=int, default=300, help="Cap tickers scanned (technical mode)")
    p_screen.add_argument("--min-composite", type=float, default=0.0, help="Min composite rank (factors mode)")
    p_screen.add_argument("--factor-filter", default=None, help="Require min rank on a specific factor (factors mode)")
    p_screen.add_argument("--min-factor-rank", type=float, default=0.0, help="Min percentile rank for --factor-filter")
    p_screen.add_argument("--json", action="store_true", help="Emit raw JSON instead of a formatted table")

    # --- Macro data adapters ---
    p_fred = sub.add_parser("fetch-macro-fred", help="Fetch macro data from FRED (Federal Reserve Economic Data)")
    p_fred.add_argument("--series", nargs="*", default=None, help="FRED series IDs (default: all configured series)")
    p_fred.add_argument("--start", default=None, help="Start date YYYY-MM-DD (default: 5 years ago)")
    p_fred.add_argument("--end", default=None, help="End date YYYY-MM-DD (default: today)")

    p_bps = sub.add_parser("fetch-macro-bps", help="Fetch macro data from BPS (Badan Pusat Statistik)")
    p_bps.add_argument("--var-id", default=None, help="BPS variable ID (single series fetch)")
    p_bps.add_argument("--series-key", default=None, help="Series key from BPS_SERIES preset (e.g. gdp_growth)")
    p_bps.add_argument("--var-ids", default=None, help="JSON mapping {series_key: var_id} for fetch-all mode")

    p_bi = sub.add_parser("fetch-macro-bi", help="Fetch macro data from Bank Indonesia")
    p_bi.add_argument("--series", nargs="*", default=None, help="BI series keys (default: all with configured endpoints)")
    p_bi.add_argument("--start", default=None, help="Start date YYYY-MM-DD (default: 5 years ago)")
    p_bi.add_argument("--end", default=None, help="End date YYYY-MM-DD (default: today)")

    args = parser.parse_args()
    if args.cmd == "fetch":
        if args.all:
            storage = DataStorage()
            tickers = storage.list_active_equity_tickers()
            print(f"Fetching {len(tickers)} active equity tickers...")
            fetch_and_store(tickers, args.period)
        elif args.tickers:
            fetch_and_store(args.tickers, args.period)
        else:
            print("Error: provide tickers or use --all")
    elif args.cmd == "list":
        list_tickers()
    elif args.cmd == "compute-scores":
        if args.all:
            storage = DataStorage()
            tickers = storage.list_active_equity_tickers()
            print(f"Computing scores for {len(tickers)} active equity tickers...")
            ok, fail = 0, 0
            for i, t in enumerate(tickers, 1):
                try:
                    pipeline = AnalysisPipeline()
                    result = pipeline.compute(t, args.period)
                    if result["status"] == "ok":
                        ok += 1
                        print(f"  [{i}/{len(tickers)}] {t}: OK")
                    else:
                        fail += 1
                        print(f"  [{i}/{len(tickers)}] {t}: FAIL ({result.get('message', 'unknown')})")
                except Exception as e:
                    fail += 1
                    print(f"  [{i}/{len(tickers)}] {t}: ERROR ({e})")
            print(f"\nDone: {ok} succeeded, {fail} failed.")
        elif args.ticker:
            compute_scores(args.ticker, args.period)
        else:
            print("Error: provide a ticker or use --all")
    elif args.cmd == "corporate-actions":
        corp = CorporateActionEngine()
        result = corp.fetch(args.ticker)
        print(result)
    elif args.cmd == "update-adjusted-close":
        storage = DataStorage()
        n = storage.update_adjusted_close(args.ticker)
        print(f"Updated adjusted_close for {n} rows of {args.ticker}")
    elif args.cmd == "import-legacy":
        from trading_system.data.import_legacy import run_import
        run_import(source_db=args.source)
    elif args.cmd == "relationship":
        rel = MarketRelationshipEngine(window=args.window)
        result = rel.compute(args.ticker)
        print(f"Relationship score: {result.get('score')}")
        for r in result.get("relationships", []):
            print(f"  {r['asset']} ({r['ticker']}): corr={r['correlation']} lag={r['lag']}")
    elif args.cmd == "recommend":
        recommend(args.ticker, args.capital)
    elif args.cmd == "explain":
        dec = DecisionEngine().recommend(args.ticker)
        if dec["status"] == "error":
            print(f"Error: {dec['message']}")
        else:
            exp = ExplainableAIEngine().explain(args.ticker, dec["recommendation"])
            print(exp.get("narrative"))
            print(exp.get("top_factors"))
    elif args.cmd == "monitor":
        print(MonitoringEngine().health())
    elif args.cmd == "paper-trade":
        print(PaperTradingEngine(cash=args.capital).simulate(args.ticker))
    elif args.cmd == "backtest":
        from trading_system.backtest.metrics import monte_carlo_simulation, walk_forward_analysis

        engine = BacktestEngine()

        if args.strategy == "buy_and_hold":
            strategy = BuyAndHold()
        elif args.strategy == "ma_crossover":
            strategy = MovingAverageCrossover()
        elif args.strategy == "conviction":
            from trading_system.backtest.strategies import ConvictionStrategy
            strategy = ConvictionStrategy(storage=engine.storage)
        else:
            print(f"Unknown strategy: {args.strategy}")
            return
        result = engine.run(args.ticker, strategy, initial_capital=args.capital)

        if result.get("status") != "ok":
            print(f"Error: {result.get('message')}")
            return

        print(f"\n{'='*60}")
        print(f"Backtest: {args.ticker} | Strategy: {result['strategy']}")
        print(f"{'='*60}")
        print(f"Final Equity: Rp {result['final_equity']:,.0f}")
        m = result.get('metrics', {})
        print(f"Total Return: {m.get('total_return', 0)*100:.2f}%")
        print(f"CAGR: {m.get('cagr', 0)*100:.2f}%")
        print(f"Sharpe: {m.get('sharpe_ratio', 0):.4f}")
        print(f"Sortino: {m.get('sortino_ratio', 0):.4f}")
        print(f"Calmar: {m.get('calmar_ratio', 0):.4f}")
        print(f"Max Drawdown: {m.get('max_drawdown', 0)*100:.2f}%")
        print(f"Win Rate: {m.get('win_rate', 0)*100:.1f}%")
        print(f"Profit Factor: {m.get('profit_factor', 'N/A')}")
        print(f"Trades: {m.get('number_of_trades', 0)}")

        if args.monte_carlo:
            print(f"\n{'='*60}")
            print(f"Monte Carlo Simulation ({args.n_simulations} runs)")
            print(f"{'='*60}")
            equity = result.get('equity_curve')
            if equity is not None and not equity.empty:
                returns = equity.pct_change().dropna()
                mc = monte_carlo_simulation(returns, n_simulations=args.n_simulations, block_size=args.block_size)
                if mc.get('status') != 'insufficient_data':
                    print(f"Mean Final Equity: Rp {mc['mean_final_equity']:,.0f}")
                    print(f"Median Final Equity: Rp {mc['median_final_equity']:,.0f}")
                    print(f"5th Percentile (Worst): Rp {mc['final_equity']['p5']:,.0f}")
                    print(f"95th Percentile (Best): Rp {mc['final_equity']['p95']:,.0f}")
                    print(f"Prob Profit: {mc['prob_profit']*100:.1f}%")
                    print(f"Prob Loss >20%: {mc['prob_loss_20pct']*100:.1f}%")
                    print(f"Worst Drawdown: {mc['worst_drawdown']*100:.2f}%")
                else:
                    print("Insufficient data for Monte Carlo")

        if args.walk_forward:
            print(f"\n{'='*60}")
            print(f"Walk-Forward Analysis ({args.n_splits} splits)")
            print(f"{'='*60}")
            df = engine.storage.load_ohlcv(args.ticker)
            if not df.empty:
                wf = walk_forward_analysis(
                    df, lambda: MovingAverageCrossover(),
                    n_splits=args.n_splits,
                )
                if wf.get('status') != 'insufficient_data' and wf.get('status') != 'no_valid_splits':
                    print(f"OOS Mean Return: {wf['oos_mean_return']*100:.2f}%")
                    print(f"OOS Std Return: {wf['oos_std_return']*100:.2f}%")
                    print(f"OOS Mean Sharpe: {wf['oos_mean_sharpe']:.4f}")
                    print(f"Positive Splits: {wf['oos_positive_splits']}/{wf['n_splits']}")
                    print(f"Consistency: {wf['oos_consistency']*100:.1f}%")
                    for s in wf['splits']:
                        print(f"  Split {s['split']}: {s['test_period']} | return={s['oos_return']*100:.2f}% | sharpe={s['oos_sharpe']:.4f}")
                else:
                    print(f"Insufficient data for walk-forward: {wf.get('status')}")
            else:
                print("No data for walk-forward")
    elif args.cmd == "execution":
        from trading_system.execution.automated import AutomatedExecutionEngine
        engine = AutomatedExecutionEngine()
        if args.once:
            results = engine.run_once(args.tickers)
            for r in results:
                print(r)
        else:
            engine.start_scheduler(interval_minutes=args.interval, tickers=args.tickers)
    elif args.cmd == "test-e2e":
        from scripts.test_end_to_end import run_e2e_test
        success = run_e2e_test(args.tickers)
        import sys
        sys.exit(0 if success else 1)
    elif args.cmd == "fetch-idx-foreign-flow":
        from trading_system.data.idx_batch import IDXBatchEngine

        engine = IDXBatchEngine(delay=args.delay)
        result = engine.scrape_foreign_flow(start_date=args.start, end_date=args.end, tickers=args.tickers)
        print(result)
    elif args.cmd == "fetch-idx-broker-flow":
        from trading_system.data.idx_batch import IDXBatchEngine

        engine = IDXBatchEngine(delay=args.delay)
        result = engine.scrape_broker_flow(start_date=args.start, end_date=args.end)
        print(result)
    elif args.cmd == "schedule":
        import os
        if args.once:
            os.environ["DAILY_RUNNER_ONCE"] = "1"
        from scripts.daily_runner import run_once_mode, run_scheduler_mode
        if os.getenv("DAILY_RUNNER_ONCE") == "1":
            run_once_mode()
        else:
            run_scheduler_mode()
    elif args.cmd == "data-status":
        storage = DataStorage()
        df = storage.get_data_freshness(table_name=args.table)
        if df.empty:
            print(f"No watermark data found for table '{args.table}'.")
            print("Watermarks are created automatically when data is fetched via daily runner or CLI.")
            print("To populate watermarks for existing data, run: python -m trading_system.cli catch-up --tickers BBCA.JK")
            return
        if args.stale_only:
            df = df[df["days_behind"] > 1]
        print(f"\n{'='*80}")
        print(f"Data Freshness Report — table: {args.table}")
        print(f"{'='*80}")
        print(f"Total tickers: {len(df)}")
        if not df.empty:
            print(f"Up to date (<=1 day): {(df['days_behind'] <= 1).sum()}")
            print(f"Stale (2-7 days):     {((df['days_behind'] > 1) & (df['days_behind'] <= 7)).sum()}")
            print(f"Stale (8-30 days):    {((df['days_behind'] > 7) & (df['days_behind'] <= 30)).sum()}")
            print(f"Very stale (>30 days):{(df['days_behind'] > 30).sum()}")
            print()
            show = df.head(args.limit) if not args.stale_only else df.head(args.limit)
            print(show.to_string(index=False))
            if len(df) > args.limit:
                print(f"\n... showing {args.limit} of {len(df)} tickers. Use --limit to see more.")
        else:
            print("All tickers are up to date!")
    elif args.cmd == "catch-up":
        storage = DataStorage()
        validator = DataQualityValidator()
        adapter = YahooFinanceAdapter()
        delisted = storage.load_delisted_tickers()
        if args.tickers:
            # Filter out delisted tickers from manual list
            all_tickers = args.tickers
            stale = [t for t in all_tickers if t.replace(".JK", "") not in delisted]
            skipped_delisted = len(all_tickers) - len(stale)
            if skipped_delisted > 0:
                print(f"Skipping {skipped_delisted} delisted tickers.")
        else:
            stale = storage.get_stale_data_tickers(max_days_behind=args.max_days)
        if not stale:
            print("All tickers are up to date — nothing to catch up.")
            return
        print(f"\n{'='*60}")
        print(f"Catch-up: {len(stale)} tickers with stale data")
        print(f"{'='*60}")
        ok = 0
        fail = 0
        for i, ticker in enumerate(stale):
            print(f"  [{i+1}/{len(stale)}] {ticker}...", end=" ")
            try:
                watermark = storage.get_watermark(ticker)
                if watermark:
                    result = adapter.fetch_incremental(ticker, last_timestamp=watermark)
                else:
                    result = adapter.fetch(ticker, period=args.period)
                if result["status"] == "ok":
                    raw = normalize_ohlcv(result["records"])
                    clean, report = validator.validate(raw)
                    if report.action == "pause":
                        print(f"SKIP (quality={report.data_quality_score})")
                        fail += 1
                        continue
                    n = storage.save_ohlcv(clean)
                    print(f"OK ({n} rows, quality={report.data_quality_score})")
                    ok += 1
                else:
                    print(f"FAIL ({result['message']})")
                    fail += 1
            except Exception as e:
                print(f"ERROR ({e})")
                fail += 1
        print(f"\nDone: {ok} succeeded, {fail} failed.")
    elif args.cmd == "screen":
        import json as _json

        storage = DataStorage()
        universe = args.tickers if args.tickers else storage.list_active_equity_tickers()
        if not universe:
            print("No tickers available.")
            return

        if args.mode == "factors":
            from trading_system.analysis.factor_engine import FactorEngine
            from trading_system.analysis.factor_screener import FactorScreenerService

            engine = FactorEngine(storage=storage)
            service = FactorScreenerService(engine)
            result = service.screen(
                top_n=args.top,
                min_composite=args.min_composite,
                factor_filter=args.factor_filter,
                min_factor_rank=args.min_factor_rank,
                tickers=universe,
            )
            if args.json:
                print(_json.dumps(result, indent=2, default=str))
                return
            print(f"\n{'='*70}")
            print(f"Factor Screen — top {result['screened_count']} of {result['scored_instruments']} scored "
                  f"(universe {result['universe_size']}, as_of {result['as_of']})")
            print(f"Factor version: {result['factor_version']} | "
                  f"skipped liquidity: {result['skipped_liquidity']}, history: {result['skipped_history']}")
            print(f"{'='*70}")
            print(f"{'#':>3}  {'Ticker':<10} {'Composite':>9}  Top factors (percentile)")
            print("-" * 70)
            for i, r in enumerate(result["results"], 1):
                fb = r.get("factor_breakdown", {}) or {}
                top = sorted(fb.items(), key=lambda kv: (kv[1].get("percentile_rank") or 0), reverse=True)[:3]
                top_str = ", ".join(f"{k}={v['percentile_rank']:.2f}" for k, v in top) if top else "—"
                print(f"{i:>3}  {r['symbol']:<10} {r['composite_rank']:>9.4f}  {top_str}")
        else:
            from trading_system.analysis.screener import TEMPLATES

            if args.template not in TEMPLATES:
                print(f"Unknown template: {args.template}. Available: {list(TEMPLATES.keys())}")
                return
            # Reuse helper dari API module untuk konsistensi kolom.
            from trading_system.api.app import _build_technical_features, _enrich_value_features

            features = _build_technical_features(universe, limit=args.max_tickers)
            if features.empty:
                print("No features could be computed (insufficient data).")
                return
            if args.template == "value":
                features = _enrich_value_features(features)
            result = TEMPLATES[args.template](features)
            if result.empty:
                print(f"Template '{args.template}': 0 of {len(features)} tickers passed.")
                return
            result = result.sort_values("score", ascending=False).reset_index(drop=True)
            result["rank"] = result.index + 1
            if args.json:
                print(_json.dumps(result.to_dict(orient="records"), indent=2, default=str))
                return
            print(f"\n{'='*70}")
            print(f"Technical Screen — template '{args.template}': "
                  f"{len(result)} of {len(features)} tickers passed")
            print(f"{'='*70}")
            cols = ["rank", "ticker", "score", "close", "rsi_14", "adx_14", "volume"]
            if args.template == "momentum":
                cols = ["rank", "ticker", "score", "close", "rsi_14", "adx_14", "macd_hist"]
            elif args.template == "value":
                cols = ["rank", "ticker", "score", "close", "per", "roe", "der"]
            cols = [c for c in cols if c in result.columns]
            print(result[cols].head(args.top).to_string(index=False))
    elif args.cmd == "fetch-macro-fred":
        from trading_system.data.macro_adapters import FREDAdapter, FRED_SERIES

        adapter = FREDAdapter()
        if not adapter.api_key:
            print("Error: FRED_API_KEY not set. Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html")
            return
        series_ids = args.series if args.series else list(FRED_SERIES.keys())
        print(f"Fetching {len(series_ids)} FRED series...")
        for sid in series_ids:
            result = adapter.fetch_series(sid, observation_start=args.start, observation_end=args.end)
            status = result["status"]
            msg = result.get("message", "")
            print(f"  {sid}: {status} — {msg}")
    elif args.cmd == "fetch-macro-bps":
        from trading_system.data.macro_adapters import BPSAdapter
        import json as _json_bps

        adapter = BPSAdapter()
        if not adapter.api_key:
            print("Error: BPS_API_KEY not set. Register at https://webapi.bps.go.id/v1/")
            return
        if args.series_key and args.var_id:
            result = adapter.fetch_series(args.series_key, args.var_id)
            print(f"  {args.series_key}: {result['status']} — {result.get('message', '')}")
        elif args.var_ids:
            var_map = _json_bps.loads(args.var_ids)
            results = adapter.fetch_all(var_map)
            for sk, res in results.items():
                print(f"  {sk}: {res['status']} — {res.get('message', '')}")
        else:
            print("Error: provide --series-key + --var-id for single fetch, or --var-ids JSON for batch")
            print("Example: --series-key gdp_growth --var-id 1234")
            print("Example: --var-ids '{\"gdp_growth\": \"1234\", \"inflation_yoy\": \"5678\"}'")
    elif args.cmd == "fetch-macro-bi":
        from trading_system.data.macro_adapters import BIAdapter, BI_ENDPOINTS

        adapter = BIAdapter()
        series_keys = args.series if args.series else list(BI_ENDPOINTS.keys())
        print(f"Fetching {len(series_keys)} Bank Indonesia series...")
        for sk in series_keys:
            result = adapter.fetch_series(sk, start_date=args.start, end_date=args.end)
            status = result["status"]
            msg = result.get("message", "")
            print(f"  {sk}: {status} — {msg}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
