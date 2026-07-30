"""CLI untuk Phase 1: fetch data, validate, backtest."""

import argparse
import sys
from pathlib import Path

# Add src to path when running as script
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd

from trading_system.data.acquisition import YahooFinanceAdapter, normalize_ohlcv
from trading_system.data.storage import DataStorage
from trading_system.data.validation import DataQualityValidator
from trading_system.backtest.engine import BacktestEngine, CostModel
from trading_system.backtest.strategies import BuyAndHold, MovingAverageCrossover
from trading_system.analysis.pipeline import AnalysisPipeline
from trading_system.corporate.actions import CorporateActionEngine
from trading_system.intelligence.relationship import MarketRelationshipEngine
from trading_system.decision.engine import DecisionEngine
from trading_system.xai.engine import ExplainableAIEngine
from trading_system.monitoring.engine import MonitoringEngine
from trading_system.paper_trading.engine import PaperTradingEngine
from trading_system.config import DEFAULT_BENCHMARK


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
                print(f"  FAILED quality ({report.data_quality_score}): {report.anomalies}")
                continue
            n = storage.save_ohlcv(clean)
            print(f"  Saved {n} rows for {t}. Quality={report.data_quality_score}")
        else:
            print(f"  Error: {result['message']}")


def backtest(ticker, strategy_name, capital=1_000_000_000):
    engine = BacktestEngine()
    if strategy_name == "buy_and_hold":
        strategy = BuyAndHold()
    elif strategy_name == "ma_crossover":
        strategy = MovingAverageCrossover(20, 50)
    else:
        print("Unknown strategy. Use buy_and_hold or ma_crossover")
        return
    result = engine.run(ticker, strategy, initial_capital=capital)
    if result["status"] == "error":
        print(f"Error: {result['message']}")
        return
    print(f"\nBacktest {ticker} with {strategy_name}")
    print(f"Final Equity: {result['final_equity']:,.0f}")
    for k, v in result["metrics"].items():
        print(f"  {k}: {v}")


def list_tickers():
    s = DataStorage()
    print(s.list_tickers())


def recommend(ticker: str, capital: float = 1_000_000_000):
    engine = DecisionEngine()
    result = engine.recommend(ticker)
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
    p_backtest.add_argument("--strategy", default="buy_and_hold", help="buy_and_hold or ma_crossover")
    p_backtest.add_argument("--capital", type=float, default=1_000_000_000)

    p_list = sub.add_parser("list", help="List tickers in DB")

    p_scores = sub.add_parser("compute-scores", help="Compute technical/fundamental/macro/global/relationship/sentiment scores")
    p_scores.add_argument("ticker", help="Ticker to analyze")
    p_scores.add_argument("--period", default="2y", help="Data period for OHLCV")

    p_corp = sub.add_parser("corporate-actions", help="Fetch and list corporate actions")
    p_corp.add_argument("ticker", help="Ticker")

    p_rel = sub.add_parser("relationship", help="Compute rolling correlation with global/macro assets")
    p_rel.add_argument("ticker", help="Ticker")
    p_rel.add_argument("--window", type=int, default=60, help="Rolling window")

    p_rec = sub.add_parser("recommend", help="Generate BUY/HOLD/SELL recommendation")
    p_rec.add_argument("ticker", help="Ticker")
    p_rec.add_argument("--capital", type=float, default=1_000_000_000)

    p_exp = sub.add_parser("explain", help="Explain recommendation for a ticker")
    p_exp.add_argument("ticker", help="Ticker")

    p_mon = sub.add_parser("monitor", help="System health check")

    p_paper = sub.add_parser("paper-trade", help="Simulate paper trade")
    p_paper.add_argument("ticker", help="Ticker")
    p_paper.add_argument("--capital", type=float, default=1_000_000_000)

    args = parser.parse_args()
    if args.cmd == "fetch":
        fetch_and_store(args.tickers, args.period)
    elif args.cmd == "backtest":
        backtest(args.ticker, args.strategy, args.capital)
    elif args.cmd == "list":
        list_tickers()
    elif args.cmd == "compute-scores":
        compute_scores(args.ticker, args.period)
    elif args.cmd == "corporate-actions":
        corp = CorporateActionEngine()
        result = corp.fetch(args.ticker)
        print(result)
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
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
