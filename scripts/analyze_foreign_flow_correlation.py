"""Analisis korelasi foreign flow vs harga saham IDX.

Mengukur apakah foreign net flow hari ini memprediksi return 1/3/5/10 hari ke depan.
Output: tabel korelasi per ticker + heatmap ke file.

Usage:
    python scripts/analyze_foreign_flow_correlation.py
    python scripts/analyze_foreign_flow_correlation.py --tickers BBCA BBRI TLKM
    python scripts/analyze_foreign_flow_correlation.py --output reports/ff_corr.html
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trading_system.data.storage import DataStorage

DEFAULT_TICKERS = [
    "BBCA", "BBRI", "BMRI", "TLKM", "ASII", "UNVR", "ANTM",
    "GOTO", "BULL", "MDKA", "ICBP", "GGRM", "KLBF", "CPIN",
    "ADRO", "PTBA", "MEDC", "PGAS", "INCO", "TINS",
]

FORWARD_HORIZONS = [1, 3, 5, 10, 20]


def load_pair(storage: DataStorage, ticker: str) -> pd.DataFrame | None:
    """Load foreign flow + OHLCV untuk satu ticker, di-merge pada date."""
    code = ticker.replace(".JK", "")
    ff = storage.load_foreign_flow(code, source="idx_scraper")
    if ff.empty:
        return None
    ff["date"] = pd.to_datetime(ff["date"])
    ff = ff.sort_values("date").set_index("date")

    ohlcv = storage.load_ohlcv(f"{code}.JK")
    if ohlcv.empty:
        return None
    ohlcv = ohlcv.copy()
    ohlcv.index = pd.to_datetime(ohlcv.index).tz_localize(None)
    ohlcv = ohlcv[~ohlcv.index.duplicated(keep="last")]

    # Merge on date
    df = ff.join(ohlcv[["close"]], how="inner")
    if len(df) < 30:
        return None

    # Compute forward returns
    df["ret_1d"] = df["close"].pct_change(1).shift(-1)
    df["ret_3d"] = df["close"].pct_change(3).shift(-3)
    df["ret_5d"] = df["close"].pct_change(5).shift(-5)
    df["ret_10d"] = df["close"].pct_change(10).shift(-10)
    df["ret_20d"] = df["close"].pct_change(20).shift(-20)

    # Normalize foreign_net by total flow
    total = df["foreign_buy"] + df["foreign_sell"]
    df["net_ratio"] = np.where(total > 0, df["foreign_net"] / total, 0.0)

    return df


def compute_correlations(df: pd.DataFrame, ticker: str) -> dict:
    """Hitung korelasi Pearson antara foreign_net/net_ratio vs forward returns."""
    result = {"ticker": ticker, "n_days": len(df)}
    for h in FORWARD_HORIZONS:
        col = f"ret_{h}d"
        valid = df[["foreign_net", "net_ratio", col]].dropna()
        if len(valid) < 30:
            result[f"corr_net_{h}d"] = np.nan
            result[f"corr_ratio_{h}d"] = np.nan
            result[f"pct_pos_{h}d"] = np.nan
        else:
            result[f"corr_net_{h}d"] = round(valid["foreign_net"].corr(valid[col]), 4)
            result[f"corr_ratio_{h}d"] = round(valid["net_ratio"].corr(valid[col]), 4)
            # % days where positive foreign net → positive return
            pos_ff = valid[valid["foreign_net"] > 0]
            if len(pos_ff) > 0:
                result[f"pct_pos_{h}d"] = round((pos_ff[col] > 0).mean(), 4)
            else:
                result[f"pct_pos_{h}d"] = np.nan
    return result


def compute_persistence(df: pd.DataFrame, ticker: str) -> dict:
    """Pola persistence: apakah foreign net buy hari ini → net buy besok?"""
    df = df.copy()
    df["ff_sign"] = np.sign(df["foreign_net"])
    df["ff_next_sign"] = df["ff_sign"].shift(-1)
    valid = df[["ff_sign", "ff_next_sign"]].dropna()
    if len(valid) < 30:
        return {"ticker": ticker, "persistence": np.nan}
    same_sign = (valid["ff_sign"] == valid["ff_next_sign"]).mean()
    return {"ticker": ticker, "persistence": round(same_sign, 4)}


def main():
    parser = argparse.ArgumentParser(description="Foreign flow vs price correlation analysis")
    parser.add_argument("--tickers", nargs="*", default=DEFAULT_TICKERS)
    parser.add_argument("--output", default="reports/foreign_flow_correlation.csv")
    parser.add_argument("--heatmap", default="reports/foreign_flow_heatmap.png")
    args = parser.parse_args()

    storage = DataStorage()
    results = []
    persistence_results = []

    print(f"Analyzing {len(args.tickers)} tickers...")
    print(f"{'Ticker':<8} {'Days':>6} {'net_1d':>8} {'ratio_1d':>10} {'net_5d':>8} {'net_10d':>9} {'pct_pos_5d':>11}")
    print("-" * 75)

    for t in args.tickers:
        df = load_pair(storage, t)
        if df is None:
            print(f"{t:<8} {'NO DATA':>6}")
            continue
        corr = compute_correlations(df, t)
        pers = compute_persistence(df, t)
        results.append(corr)
        persistence_results.append(pers)
        print(
            f"{t:<8} {corr['n_days']:>6} "
            f"{corr.get('corr_net_1d', float('nan')):>8} "
            f"{corr.get('corr_ratio_1d', float('nan')):>10} "
            f"{corr.get('corr_net_5d', float('nan')):>8} "
            f"{corr.get('corr_net_10d', float('nan')):>9} "
            f"{corr.get('pct_pos_5d', float('nan')):>11}"
        )

    if not results:
        print("\nNo data to analyze.")
        return

    # Save CSV
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_out = pd.DataFrame(results)
    df_out.to_csv(out_path, index=False)
    print(f"\nCorrelation table saved to: {out_path}")

    # Persistence
    df_pers = pd.DataFrame(persistence_results)
    pers_path = out_path.parent / "foreign_flow_persistence.csv"
    df_pers.to_csv(pers_path, index=False)
    print(f"Persistence table saved to: {pers_path}")

    # Heatmap
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import seaborn as sns

        cols = [f"corr_net_{h}d" for h in FORWARD_HORIZONS]
        labels = [f"{h}d forward" for h in FORWARD_HORIZONS]
        heat_data = df_out.set_index("ticker")[cols].astype(float)
        heat_data.columns = labels

        plt.figure(figsize=(10, max(6, len(heat_data) * 0.4)))
        sns.heatmap(heat_data, annot=True, fmt=".3f", cmap="RdYlGn", center=0, vmin=-0.3, vmax=0.3)
        plt.title("Correlation: Foreign Net Flow → Forward Returns")
        plt.ylabel("Ticker")
        plt.xlabel("Forward Return Horizon")
        plt.tight_layout()
        heat_path = Path(args.heatmap)
        heat_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(heat_path, dpi=120)
        print(f"Heatmap saved to: {heat_path}")
    except ImportError:
        print("matplotlib/seaborn not installed — skipping heatmap")

    # Summary stats
    print(f"\n{'='*75}")
    print("SUMMARY")
    print(f"{'='*75}")
    for h in FORWARD_HORIZONS:
        col = f"corr_net_{h}d"
        vals = df_out[col].dropna()
        if len(vals) > 0:
            print(f"  {h:>2}d forward: mean_corr={vals.mean():+.4f}  "
                  f"max={vals.max():+.4f} ({df_out.loc[vals.idxmax(), 'ticker']})  "
                  f"min={vals.min():+.4f} ({df_out.loc[vals.idxmin(), 'ticker']})")

    pers_vals = df_pers["persistence"].dropna()
    if len(pers_vals) > 0:
        print("\n  Foreign flow persistence (prob same sign next day):")
        print(f"    mean={pers_vals.mean():.2%}  max={pers_vals.max():.2%}  min={pers_vals.min():.2%}")


if __name__ == "__main__":
    main()
