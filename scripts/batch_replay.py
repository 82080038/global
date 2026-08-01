"""Batch replay simulation for all tickers with pre-computed scores.

Menjalankan replay untuk semua ticker yang punya scores di DB,
menyimpan hasil ke file JSON terpisah, lalu membuat summary perbandingan.

Penggunaan:
    ./venv/bin/python scripts/batch_replay.py [--capital 10000000] [--months 12]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trading_system.data.storage import DataStorage


def main():
    parser = argparse.ArgumentParser(description="Batch replay simulation")
    parser.add_argument("--capital", type=float, default=10_000_000)
    parser.add_argument("--months", type=int, default=12)
    args = parser.parse_args()

    # Find all tickers with scores
    storage = DataStorage()
    with storage._connect() as conn:
        rows = conn.execute("SELECT DISTINCT ticker FROM scores").fetchall()
    scored_tickers = sorted([r[0] for r in rows])
    print(f"Tickers with scores: {scored_tickers}")
    print(f"Running replay for {len(scored_tickers)} tickers with capital Rp {args.capital:,.0f}")
    print("=" * 70)

    # Import here to avoid circular import issues
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from replay_simulation import ReplaySimulation

    all_results = []
    results_dir = Path(__file__).parent / "replay_results"
    results_dir.mkdir(exist_ok=True)

    for i, ticker in enumerate(scored_tickers):
        print(f"\n[{i+1}/{len(scored_tickers)}] {ticker}")
        print("-" * 40)

        try:
            sim = ReplaySimulation(
                ticker=ticker,
                capital=args.capital,
                months=args.months,
                storage=storage,
            )
            results = sim.run(clean=True)

            if results["status"] == "ok":
                # Save individual result (include daily_records for visualization)
                result_file = results_dir / f"replay_{ticker.replace('.', '_')}.json"
                serializable = {k: v for k, v in results.items() if k not in ("trades", "equity_curve", "daily_records")}
                serializable["trades"] = results["trades"]
                serializable["equity_curve"] = results["equity_curve"]
                serializable["daily_records"] = results["daily_records"]
                with open(result_file, "w") as f:
                    json.dump(serializable, f, indent=2, default=str)

                all_results.append({
                    "ticker": ticker,
                    "final_equity": results["final_equity"],
                    "total_return_pct": results["total_return_pct"],
                    "total_realized_pnl": results["total_realized_pnl"],
                    "total_fees": results["total_fees"],
                    "sharpe_ratio": results["sharpe_ratio"],
                    "max_drawdown_pct": results["max_drawdown_pct"],
                    "n_buys": results["n_buys"],
                    "n_sells": results["n_sells"],
                    "n_stop_loss": results["n_stop_loss"],
                    "n_take_profit": results["n_take_profit"],
                    "n_trailing_stop": results["n_trailing_stop"],
                    "n_trading_days": results["n_trading_days"],
                })
                print(f"  Result: {results['total_return_pct']:+.2f}% | Sharpe={results['sharpe_ratio']:.4f} | Trades={results['n_buys']}B/{results['n_sells']}S")
            else:
                print(f"  ERROR: {results.get('message')}")
                all_results.append({"ticker": ticker, "status": "error", "message": results.get("message")})

        except Exception as e:
            print(f"  EXCEPTION: {e}")
            all_results.append({"ticker": ticker, "status": "error", "message": str(e)})

    # Save summary
    summary_file = results_dir / "summary.json"
    with open(summary_file, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    # Print summary table
    print("\n" + "=" * 70)
    print("BATCH REPLAY SUMMARY")
    print("=" * 70)
    print(f"{'Ticker':<12} {'Return':>8} {'Sharpe':>8} {'MaxDD':>8} {'Trades':>8} {'SL/TP/TS':>10} {'Final Equity':>15}")
    print("-" * 70)

    for r in sorted(all_results, key=lambda x: x.get("total_return_pct", -999), reverse=True):
        if r.get("status") == "error":
            print(f"{r['ticker']:<12} ERROR")
            continue
        trades = f"{r['n_buys']}B/{r['n_sells']}S"
        sl_tp_ts = f"{r['n_stop_loss']}/{r['n_take_profit']}/{r['n_trailing_stop']}"
        print(
            f"{r['ticker']:<12} {r['total_return_pct']:>+7.2f}% {r['sharpe_ratio']:>8.4f} "
            f"{r['max_drawdown_pct']:>7.2f}% {trades:>8} {sl_tp_ts:>10} Rp {r['final_equity']:>12,.0f}"
        )

    print("=" * 70)
    print(f"Results saved to: {results_dir}/")
    print(f"Summary: {summary_file}")


if __name__ == "__main__":
    main()
