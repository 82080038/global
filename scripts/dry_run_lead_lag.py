"""Dry run lead-lag analysis antar saham IDX.

Menggunakan LeadLagAnalyzer dari trading_system.analysis.lead_lag untuk
identifikasi saham "leader" vs "follower" berdasarkan cross-correlation
return pada berbagai offset hari.

Output:
- Top 20 pasangan dengan korelasi lead-lag tertinggi
- Leader board: saham yang paling sering memimpin
- Follower board: saham yang paling sering mengikuti

Usage:
    python scripts/dry_run_lead_lag.py
    python scripts/dry_run_lead_lag.py --tickers BBCA BBRI TLKM ASII
    python scripts/dry_run_lead_lag.py --max-offset 5 --min-bars 200
"""

from __future__ import annotations

import argparse
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trading_system.analysis.lead_lag import LeadLagAnalyzer
from trading_system.data.storage import DataStorage

DEFAULT_TICKERS = [
    "BBCA.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "ASII.JK", "UNVR.JK",
    "ANTM.JK", "ICBP.JK", "GGRM.JK", "KLBF.JK", "CPIN.JK", "ADRO.JK",
    "PTBA.JK", "MDKA.JK", "MEDC.JK", "PGAS.JK", "INCO.JK", "TINS.JK",
    "INDF.JK", "MYOR.JK",
]


def load_returns(storage: DataStorage, tickers: list[str], min_bars: int) -> dict[str, np.ndarray]:
    """Load daily returns untuk setiap ticker."""
    returns_data = {}
    skipped = []
    for t in tickers:
        df = storage.load_ohlcv(t)
        if df.empty or len(df) < min_bars:
            skipped.append(t)
            continue
        df = df.sort_index()
        closes = df["close"].values.astype(float)
        rets = np.diff(closes) / closes[:-1]
        rets = np.nan_to_num(rets, nan=0.0)
        returns_data[t] = rets
    if skipped:
        print(f"  Skipped (insufficient data, < {min_bars} bars): {', '.join(skipped)}")
    return returns_data


def main():
    parser = argparse.ArgumentParser(description="Dry run lead-lag analysis antar saham IDX")
    parser.add_argument("--tickers", nargs="*", default=DEFAULT_TICKERS)
    parser.add_argument("--max-offset", type=int, default=10, help="Max day offset for cross-correlation")
    parser.add_argument("--min-bars", type=int, default=200, help="Minimum bars required")
    parser.add_argument("--corr-threshold", type=float, default=0.3, help="Min |corr| to be significant")
    parser.add_argument("--top-n", type=int, default=20, help="Number of top pairs to show")
    parser.add_argument("--output", default="reports/lead_lag_results.csv")
    args = parser.parse_args()

    storage = DataStorage()

    print(f"Loading returns for {len(args.tickers)} tickers...")
    returns_data = load_returns(storage, args.tickers, args.min_bars)
    if len(returns_data) < 2:
        print("Need at least 2 tickers with sufficient data.")
        return

    print(f"Analyzing lead-lag for {len(returns_data)} tickers...")
    print(f"  Pairs to analyze: {len(list(combinations(returns_data.keys(), 2)))}")
    print(f"  Max offset: ±{args.max_offset} days")
    print(f"  Min bars: {args.min_bars}")
    print(f"  Corr threshold: {args.corr_threshold}")
    print()

    analyzer = LeadLagAnalyzer(
        max_offset=args.max_offset,
        min_bars=args.min_bars,
        corr_threshold=args.corr_threshold,
    )

    # Generate all pairs
    pairs = list(combinations(returns_data.keys(), 2))
    results = analyzer.analyze_multiple(returns_data, pairs)

    # Filter significant
    significant = [r for r in results if r.get("significant") and r.get("direction") != "synchronous"]
    print(f"{'='*80}")
    print(f"RESULTS: {len(significant)} significant lead-lag pairs out of {len(results)} total")
    print(f"{'='*80}")

    if not significant:
        print("No significant lead-lag relationships found at current threshold.")
        print("Try lowering --corr-threshold (e.g. 0.2) or increasing --max-offset.")
        # Still show top 10 by absolute correlation
        all_sorted = sorted(results, key=lambda r: abs(r.get("best_corr", 0)), reverse=True)
        print("\nTop 10 by |correlation| (regardless of significance):")
        print(f"  {'Leader':<12} {'Follower':<12} {'Offset':>7} {'Corr':>8} {'Direction':<15}")
        print(f"  {'-'*56}")
        for r in all_sorted[:10]:
            print(f"  {r['leader']:<12} {r['follower']:<12} {r['best_offset']:>+7} {r['best_corr']:>+8.4f} {r['direction']:<15}")
    else:
        # Sort by absolute correlation
        significant.sort(key=lambda r: abs(r["best_corr"]), reverse=True)

        print(f"\nTop {min(args.top_n, len(significant))} lead-lag pairs:")
        print(f"  {'Leader':<12} {'Follower':<12} {'Offset':>7} {'Corr':>8} {'Direction':<15}")
        print(f"  {'-'*56}")
        for r in significant[:args.top_n]:
            print(f"  {r['leader']:<12} {r['follower']:<12} {r['best_offset']:>+7} {r['best_corr']:>+8.4f} {r['direction']:<15}")

        # Leader board: saham yang paling sering memimpin
        leader_count = {}
        follower_count = {}
        for r in significant:
            if r["direction"] == "leader_leads":
                leader_count[r["leader"]] = leader_count.get(r["leader"], 0) + 1
                follower_count[r["follower"]] = follower_count.get(r["follower"], 0) + 1
            elif r["direction"] == "follower_leads":
                leader_count[r["follower"]] = leader_count.get(r["follower"], 0) + 1
                follower_count[r["leader"]] = follower_count.get(r["leader"], 0) + 1

        print(f"\n{'='*80}")
        print("LEADER BOARD (saham yang paling sering memimpin)")
        print(f"{'='*80}")
        for ticker, count in sorted(leader_count.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {ticker:<12} leads in {count} pairs")

        print(f"\n{'='*80}")
        print("FOLLOWER BOARD (saham yang paling sering mengikuti)")
        print(f"{'='*80}")
        for ticker, count in sorted(follower_count.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {ticker:<12} follows in {count} pairs")

    # Save full results
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_out = pd.DataFrame(results)
    df_out.to_csv(out_path, index=False)
    print(f"\nFull results saved to: {out_path}")

    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"  Total pairs analyzed:    {len(results)}")
    print(f"  Significant (|corr|>={args.corr_threshold}): {len(significant)}")
    print(f"  Synchronous:             {sum(1 for r in results if r.get('direction') == 'synchronous')}")
    print(f"  No relationship:         {sum(1 for r in results if not r.get('significant'))}")


if __name__ == "__main__":
    main()
