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
    print(s.list_tickers())


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
    p_fetch.add_argument("tickers", nargs="+", help="List of tickers (use .JK suffix for IDX)")
    p_fetch.add_argument("--period", default="2y", help="Yahoo Finance period")

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
    p_scores.add_argument("ticker", help="Ticker to analyze")
    p_scores.add_argument("--period", default="2y", help="Data period for OHLCV")

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

    args = parser.parse_args()
    if args.cmd == "fetch":
        fetch_and_store(args.tickers, args.period)
    elif args.cmd == "list":
        list_tickers()
    elif args.cmd == "compute-scores":
        compute_scores(args.ticker, args.period)
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
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
