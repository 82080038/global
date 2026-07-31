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

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("daily_runner")


def get_watchlist() -> list[str]:
    """Load tickers from env or return default watchlist."""
    env_tickers = os.getenv("DAILY_RUNNER_TICKERS")
    if env_tickers:
        return [t.strip() for t in env_tickers.split(",") if t.strip()]
    return ["BBCA.JK", "TLKM.JK", "ASII.JK", "UNVR.JK"]


def fetch_and_validate(tickers: list[str]) -> dict:
    """Fetch OHLCV data for all tickers."""
    from trading_system.data.acquisition import YahooFinanceAdapter, normalize_ohlcv
    from trading_system.data.storage import DataStorage
    from trading_system.data.validation import DataQualityValidator

    adapter = YahooFinanceAdapter()
    storage = DataStorage()
    validator = DataQualityValidator()
    results = {}

    for ticker in tickers:
        try:
            logger.info(f"Fetching {ticker}...")
            result = adapter.fetch(ticker, period="2y")
            if result["status"] == "ok":
                raw = normalize_ohlcv(result["records"])
                clean, report = validator.validate(raw)
                if report.action == "pause":
                    logger.warning(f"  {ticker}: FAILED quality ({report.data_quality_score}, tier={report.tier})")
                    results[ticker] = {"status": "failed", "reason": "quality_pause"}
                    continue
                n = storage.save_ohlcv(clean)
                logger.info(f"  {ticker}: Saved {n} rows. Quality={report.data_quality_score} tier={report.tier}")
                results[ticker] = {"status": "ok", "rows": n, "quality": report.data_quality_score}
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


def daily_job() -> None:
    """Run the full daily pipeline: fetch → scores → recommendations → notifications."""
    logger.info("=" * 60)
    logger.info("🔄 Memulai daily update...")
    tickers = get_watchlist()
    logger.info(f"Watchlist: {tickers}")

    # Step 1: Fetch & validate OHLCV
    logger.info("─" * 40)
    logger.info("Step 1: Fetch & Validate OHLCV")
    fetch_results = fetch_and_validate(tickers)
    ok_count = sum(1 for r in fetch_results.values() if r["status"] == "ok")
    logger.info(f"Fetch complete: {ok_count}/{len(tickers)} succeeded")

    # Step 2: Compute scores
    logger.info("─" * 40)
    logger.info("Step 2: Compute Analysis Scores")
    for ticker in tickers:
        if fetch_results.get(ticker, {}).get("status") == "ok":
            compute_scores_for_ticker(ticker)

    # Step 3: Generate recommendations
    logger.info("─" * 40)
    logger.info("Step 3: Generate Recommendations")
    recommendations = generate_recommendations(tickers)

    # Step 4: Send notifications
    logger.info("─" * 40)
    logger.info("Step 4: Send Notifications")
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
