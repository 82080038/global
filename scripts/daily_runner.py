"""Daily Runner — Scheduler otomatis untuk fetch data, compute scores, dan generate recommendations.

Jalankan dengan: python scripts/daily_runner.py
Atau sebagai Windows Task Scheduler yang memanggil script ini setiap jam 17:00 WIB.

Environment variables:
    DAILY_RUNNER_TICKERS  — comma-separated list of tickers (default: BBCA.JK,TLKM.JK,ASII.JK,UNVR.JK)
    DAILY_RUNNER_TIME      — time to run daily (default: 17:00)
    DAILY_RUNNER_ONCE      — if "1", run once and exit (for cron/Task Scheduler mode)
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Configure structured logging
from trading_system.utils.logging_config import setup_logging
setup_logging()

logger = logging.getLogger("daily_runner")


def get_watchlist() -> list[str]:
    """Load tickers from env, or return all active IDX stock tickers from DB.
    
    Priority:
    1. DAILY_RUNNER_TICKERS env var (comma-separated)
    2. All active equity tickers from instrument_master (with .JK suffix)
    """
    env_tickers = os.getenv("DAILY_RUNNER_TICKERS")
    if env_tickers:
        return [t.strip() for t in env_tickers.split(",") if t.strip()]
    
    # Load all active IDX stocks from instrument_master
    from trading_system.data.storage import DataStorage
    storage = DataStorage()
    codes = storage.load_idx_stock_tickers(active_only=True)
    # Append .JK suffix for yfinance compatibility
    tickers = [f"{c}.JK" if "." not in c else c for c in codes]
    logger.info(f"Loaded {len(tickers)} active IDX stock tickers from instrument_master")
    return tickers


def fetch_and_validate(tickers: list[str]) -> dict:
    """Fetch OHLCV data for all tickers (Parquet-first, fallback Yahoo Finance)."""
    from trading_system.data.acquisition import YahooFinanceAdapter, normalize_ohlcv
    from trading_system.data.archive import ArchiveAdapter
    from trading_system.data.storage import DataStorage
    from trading_system.data.validation import DataQualityValidator
    from datetime import datetime

    adapter = YahooFinanceAdapter()
    archive = ArchiveAdapter()
    storage = DataStorage()
    validator = DataQualityValidator()
    results = {}
    today = datetime.now().strftime("%Y-%m-%d")

    for ticker in tickers:
        try:
            logger.info(f"Fetching {ticker}...")
            # 1. Cek SQLite dulu — apakah data sudah mutakhir?
            existing = storage.load_ohlcv(ticker)
            if not existing.empty:
                last_ts = str(existing.index[-1])[:10]
                if last_ts >= today:
                    logger.info(f"  {ticker}: Already up to date ({last_ts})")
                    results[ticker] = {"status": "up_to_date", "rows": 0, "reason": "already_current"}
                    continue
                # 2. Coba Parquet archive untuk data incremental
                arch_df = archive.load_ohlcv(ticker, start=last_ts)
                if not arch_df.empty:
                    new_df = arch_df[arch_df.index > pd.Timestamp(last_ts)].copy()
                    if not new_df.empty:
                        new_df = new_df.reset_index()
                        new_df["ticker"] = ticker
                        new_df["asset_class"] = "equity"
                        new_df["exchange"] = "INDO" if ticker.endswith(".JK") else "GLOBAL"
                        new_df["timeframe"] = "1d"
                        new_df["source"] = "archive"
                        new_df["ingested_at"] = datetime.now().isoformat()
                        new_df["data_quality_score"] = None
                        raw = normalize_ohlcv(new_df)
                        clean, report = validator.validate(raw)
                        if report.action != "pause":
                            n = storage.save_ohlcv(clean)
                            logger.info(f"  {ticker}: Loaded {n} rows from Parquet archive. Quality={report.data_quality_score}")
                            results[ticker] = {"status": "ok", "rows": n, "source": "archive"}
                            continue
                # 3. Fallback: Yahoo Finance untuk data terbaru
                result = adapter.fetch_incremental(ticker, last_timestamp=last_ts)
            else:
                # SQLite kosong — coba Parquet archive dulu
                arch_df = archive.load_ohlcv(ticker)
                if not arch_df.empty:
                    arch_df = arch_df.reset_index()
                    arch_df["ticker"] = ticker
                    arch_df["asset_class"] = "equity"
                    arch_df["exchange"] = "INDO" if ticker.endswith(".JK") else "GLOBAL"
                    arch_df["timeframe"] = "1d"
                    arch_df["source"] = "archive"
                    arch_df["ingested_at"] = datetime.now().isoformat()
                    arch_df["data_quality_score"] = None
                    raw = normalize_ohlcv(arch_df)
                    clean, report = validator.validate(raw)
                    if report.action != "pause":
                        n = storage.save_ohlcv(clean)
                        logger.info(f"  {ticker}: Loaded {n} rows from Parquet archive. Quality={report.data_quality_score}")
                        results[ticker] = {"status": "ok", "rows": n, "source": "archive"}
                        continue
                # 4. Fallback terakhir: Yahoo Finance full fetch
                result = adapter.fetch(ticker, period="2y")

            if result["status"] == "ok":
                raw = normalize_ohlcv(result["records"])
                clean, report = validator.validate(raw)
                if report.action == "pause":
                    logger.warning(f"  {ticker}: FAILED quality ({report.data_quality_score}, tier={report.tier})")
                    results[ticker] = {"status": "failed", "reason": "quality_pause"}
                    continue
                n = storage.save_ohlcv(clean)
                logger.info(f"  {ticker}: Saved {n} rows from Yahoo Finance. Quality={report.data_quality_score} tier={report.tier}")
                results[ticker] = {"status": "ok", "rows": n, "source": "yahoo", "quality": report.data_quality_score}
            else:
                logger.error(f"  {ticker}: {result['message']}")
                results[ticker] = {"status": "error", "reason": result["message"]}
        except Exception as e:
            logger.error(f"  {ticker}: Exception: {e}")
            results[ticker] = {"status": "error", "reason": str(e)}

    return results


def compute_scores_for_ticker(ticker: str) -> dict:
    """Run analysis pipeline for a single ticker."""
    from trading_system.analysis.pipeline import AnalysisPipeline

    try:
        pipeline = AnalysisPipeline()
        result = pipeline.compute(ticker, period="2y")
        if result["status"] == "ok":
            logger.info(f"  {ticker}: Scores computed — {result['scores']}")
        else:
            logger.warning(f"  {ticker}: Score computation failed — {result.get('message')}")
        return result
    except Exception as e:
        logger.error(f"  {ticker}: Score computation exception: {e}")
        return {"status": "error", "message": str(e)}


def generate_recommendations(tickers: list[str]) -> list[dict]:
    """Generate recommendations for all tickers and return actionable signals."""
    from trading_system.decision.engine import DecisionEngine

    engine = DecisionEngine()
    recommendations = []

    for ticker in tickers:
        try:
            result = engine.recommend(ticker)
            if result["status"] == "ok":
                rec = result["recommendation"]
                logger.info(f"  {ticker}: {rec['action']} (conviction={rec['conviction_score']})")
                recommendations.append({
                    "ticker": ticker,
                    "action": rec["action"],
                    "conviction": rec["conviction_score"],
                    "entry_price": rec.get("entry_price_range"),
                    "stop_loss": rec.get("stop_loss"),
                    "take_profit": rec.get("take_profit"),
                    "risk_flags": rec.get("risk_flags", []),
                })
            else:
                logger.warning(f"  {ticker}: Recommendation failed — {result.get('message')}")
        except Exception as e:
            logger.error(f"  {ticker}: Recommendation exception: {e}")

    return recommendations


def send_notifications(recommendations: list[dict]) -> None:
    """Send notifications for actionable signals (BUY/SELL)."""
    try:
        from trading_system.utils.notifier import send_telegram
    except ImportError:
        logger.info("Notifier not available, skipping notifications")
        return

    actionable = [r for r in recommendations if r["action"] in ("BUY", "SELL")]
    if not actionable:
        logger.info("No actionable signals today")
        return

    for rec in actionable:
        msg = (
            f"🔔 SINYAL {rec['action']} untuk {rec['ticker']}\n"
            f"   Conviction: {rec['conviction']:.1f}\n"
            f"   Entry: {rec['entry_price']}\n"
            f"   Stop Loss: {rec['stop_loss']}\n"
            f"   Take Profit: {rec['take_profit']}\n"
            f"   Risk Flags: {rec['risk_flags']}"
        )
        send_telegram(msg)
        logger.info(f"Notification sent for {rec['ticker']}: {rec['action']}")


def run_automated_execution(tickers: list[str]) -> None:
    """Run one cycle of automated execution (monitoring mode by default)."""
    try:
        from trading_system.execution.automated import AutomatedExecutionEngine
        engine = AutomatedExecutionEngine()
        results = engine.run_once(tickers)
        actions = [r for r in results if r.get("status") not in ("no_action", "monitoring", "skipped", "circuit_breaker")]
        if actions:
            logger.info(f"Execution cycle: {len(actions)} actions taken")
        else:
            logger.info("Execution cycle: no actions (monitoring mode or no signals)")
    except Exception as e:
        logger.error(f"Automated execution failed: {e}")


def save_daily_risk_metrics() -> None:
    """Save daily portfolio risk metrics (VaR, CVaR, drawdown)."""
    try:
        from trading_system.risk.engine import RiskEngine
        engine = RiskEngine()
        engine.save_daily_risk()
        logger.info("Daily risk metrics saved")
    except Exception as e:
        logger.error(f"Daily risk metrics failed: {e}")


def save_performance_snapshot() -> None:
    """Save daily equity snapshot for performance tracking."""
    try:
        from trading_system.portfolio.performance import PerformanceAnalytics
        analytics = PerformanceAnalytics()
        equity = analytics.save_daily_snapshot()
        logger.info(f"Performance snapshot saved (equity: {equity})")
    except Exception as e:
        logger.error(f"Performance snapshot failed: {e}")


def daily_job() -> None:
    """Run the full daily pipeline: fetch → scores → recommendations → execution → risk → performance → notifications."""
    logger.info("=" * 60)
    logger.info("🔄 Memulai daily update...")
    tickers = get_watchlist()
    logger.info(f"Watchlist: {len(tickers)} tickers")
    if len(tickers) <= 10:
        logger.info(f"  {tickers}")

    # Step 1: Fetch & validate OHLCV
    logger.info("─" * 40)
    logger.info(f"Step 1: Fetch & Validate OHLCV ({len(tickers)} tickers)")
    fetch_results = fetch_and_validate(tickers)
    ok_count = sum(1 for r in fetch_results.values() if r["status"] == "ok")
    logger.info(f"Fetch complete: {ok_count}/{len(tickers)} succeeded")

    # Step 2: Compute scores (only for tickers with fresh data)
    logger.info("─" * 40)
    logger.info(f"Step 2: Compute Analysis Scores")
    scored = 0
    for i, ticker in enumerate(tickers):
        if fetch_results.get(ticker, {}).get("status") == "ok":
            compute_scores_for_ticker(ticker)
            scored += 1
        if (i + 1) % 100 == 0:
            logger.info(f"  Scored {i+1}/{len(tickers)} ({scored} with fresh data)")

    # Step 3: Generate recommendations for all active tickers with scores
    logger.info("─" * 40)
    logger.info("Step 3: Generate Recommendations")
    # Only generate recommendations for tickers that have fresh scores
    # (fetch_results status=ok means data was updated today)
    rec_tickers = [t for t in tickers if fetch_results.get(t, {}).get("status") == "ok"]
    logger.info(f"  Generating recommendations for {len(rec_tickers)} tickers with fresh data")
    recommendations = generate_recommendations(rec_tickers)

    # Step 4: Run automated execution (monitoring mode by default)
    logger.info("─" * 40)
    logger.info("Step 4: Automated Execution Cycle")
    run_automated_execution(tickers)

    # Step 5: Save daily risk metrics
    logger.info("─" * 40)
    logger.info("Step 5: Daily Risk Metrics")
    save_daily_risk_metrics()

    # Step 6: Save performance snapshot
    logger.info("─" * 40)
    logger.info("Step 6: Performance Snapshot")
    save_performance_snapshot()

    # Step 7: Render supplementary data (macro, sentiment, patterns, etc.)
    logger.info("─" * 40)
    logger.info("Step 7: Render Supplementary Data")
    try:
        from trading_system.data.storage import DataStorage as _DS
        supp_storage = _DS()
        supp_tasks = [
            "macro_data", "fear_greed", "pattern_analysis",
            "stock_personality", "market_calendar", "sector_master",
            "external_events", "policy_events",
        ]
        for task_name in supp_tasks:
            try:
                # Import render function dynamically
                import importlib.util
                spec = importlib.util.spec_from_file_location(
                    "render_data",
                    Path(__file__).parent / "render_data.py",
                )
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)

                func_name = f"render_{task_name}"
                func = getattr(mod, func_name, None)
                if func:
                    count = func(supp_storage, tickers, dry_run=False)
                    logger.info(f"  {task_name}: {count} records")
            except Exception as e:
                logger.warning(f"  {task_name}: {e}")
    except Exception as e:
        logger.error(f"Supplementary render failed: {e}")

    # Step 8: Send notifications
    logger.info("─" * 40)
    logger.info("Step 8: Send Notifications")
    send_notifications(recommendations)

    logger.info("=" * 60)
    logger.info("✅ Daily update selesai.")


def run_scheduler_mode():
    """Run as a persistent scheduler using the `schedule` library."""
    try:
        import schedule
    except ImportError:
        logger.error("Library 'schedule' tidak ditemukan. Install dengan: pip install schedule")
        sys.exit(1)

    run_time = os.getenv("DAILY_RUNNER_TIME", "17:00")
    logger.info(f"Scheduler mode: daily at {run_time} (server time)")
    schedule.every().day.at(run_time).do(daily_job)

    logger.info("Scheduler started. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        import time
        time.sleep(60)


def run_once_mode():
    """Run the daily job once and exit. Suitable for cron/Windows Task Scheduler."""
    logger.info("Once mode: running daily job immediately")
    daily_job()


if __name__ == "__main__":
    if os.getenv("DAILY_RUNNER_ONCE") == "1":
        run_once_mode()
    else:
        run_scheduler_mode()
