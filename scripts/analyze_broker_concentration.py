"""Analisis pola broker concentration & smart money persistence.

Pertanyaan yang dijawab:
1. Broker mana yang paling dominan (HHI concentration)?
2. Apakah konsentrasi broker tinggi berkorelasi dengan volatilitas pasar?
3. Persistence: broker top hari ini → masih top besok?
4. Smart money persistence: pola akumulasi/distribusi asing berkelanjutan?

Usage:
    python scripts/analyze_broker_concentration.py
    python scripts/analyze_broker_concentration.py --start 2024-01-01
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trading_system.data.storage import DataStorage


def compute_hhi(shares: np.ndarray) -> float:
    """Herfindahl-Hirschman Index: 0 = perfect competition, 1 = monopoly."""
    total = shares.sum()
    if total == 0:
        return 0.0
    p = shares / total
    return float((p ** 2).sum())


def load_broker_flow(storage: DataStorage, start: str | None = None) -> pd.DataFrame:
    """Load all broker flow data."""
    df = storage.load_broker_flow(source="idx_scraper")
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    if start:
        df = df[df["date"] >= start]
    return df


def daily_concentration(df: pd.DataFrame) -> pd.DataFrame:
    """Compute daily HHI & top broker share."""
    rows = []
    for date, group in df.groupby("date"):
        values = group["net_value"].values
        if len(values) < 2 or values.sum() == 0:
            continue
        hhi = compute_hhi(np.abs(values))
        top_share = values.max() / values.sum() if values.sum() != 0 else 0
        top_broker = group.loc[group["net_value"].idxmax(), "broker"]
        rows.append({
            "date": date,
            "n_brokers": len(group),
            "hhi": hhi,
            "top_share": top_share,
            "top_broker": top_broker,
            "total_value": values.sum(),
        })
    return pd.DataFrame(rows).sort_values("date").set_index("date")


def broker_ranking_persistence(df: pd.DataFrame, top_n: int = 5) -> dict:
    """Berapa sering broker yang top-N hari ini masih top-N besok?"""
    df = df.sort_values(["date", "net_value"], ascending=[True, False])
    dates = sorted(df["date"].unique())

    persist_count = 0
    total_pairs = 0
    broker_overlap = []

    for i in range(len(dates) - 1):
        d1, d2 = dates[i], dates[i + 1]
        top1 = df[df["date"] == d1].nlargest(top_n, "net_value")["broker"].tolist()
        top2 = df[df["date"] == d2].nlargest(top_n, "net_value")["broker"].tolist()
        if not top1 or not top2:
            continue
        overlap = len(set(top1) & set(top2))
        broker_overlap.append(overlap / top_n)
        total_pairs += 1

    if total_pairs == 0:
        return {"avg_overlap": np.nan, "total_pairs": 0}
    return {
        "avg_overlap": round(np.mean(broker_overlap), 4),
        "median_overlap": round(np.median(broker_overlap), 4),
        "total_pairs": total_pairs,
    }


def top_brokers_all_time(df: pd.DataFrame, top_n: int = 15) -> pd.DataFrame:
    """Broker terbesar sepanjang periode."""
    agg = df.groupby("broker").agg(
        total_value=("net_value", "sum"),
        total_volume=("net_volume", "sum"),
        active_days=("date", "nunique"),
        avg_daily_value=("net_value", "mean"),
    ).sort_values("total_value", ascending=False)
    return agg.head(top_n)


def concentration_vs_volatility(conc: pd.DataFrame, storage: DataStorage) -> pd.DataFrame | None:
    """Cek korelasi HHI vs IHSG volatility."""
    ihsg = storage.load_ohlcv("^JKSE")
    if ihsg.empty:
        return None
    ihsg = ihsg.copy()
    ihsg.index = pd.to_datetime(ihsg.index).tz_localize(None)
    ihsg["ret"] = ihsg["close"].pct_change()
    ihsg["vol_20d"] = ihsg["ret"].rolling(20).std()

    merged = conc.join(ihsg[["vol_20d", "ret"]], how="inner")
    return merged


def main():
    parser = argparse.ArgumentParser(description="Broker concentration & smart money pattern analysis")
    parser.add_argument("--start", default=None, help="Start date YYYY-MM-DD")
    parser.add_argument("--output", default="reports/broker_concentration.csv")
    args = parser.parse_args()

    storage = DataStorage()
    df = load_broker_flow(storage, start=args.start)
    if df.empty:
        print("No broker flow data found. Run: python -m trading_system.cli fetch-idx-broker-flow")
        return

    print(f"Loaded {len(df):,} broker flow records ({df['date'].nunique()} days, "
          f"{df['broker'].nunique()} brokers)")
    print(f"Date range: {df['date'].min().date()} to {df['date'].max().date()}\n")

    # 1. Daily concentration
    conc = daily_concentration(df)
    print(f"{'='*70}")
    print("1. DAILY BROKER CONCENTRATION (HHI)")
    print(f"{'='*70}")
    print(f"   Mean HHI:    {conc['hhi'].mean():.4f}  (0=perfect competition, 1=monopoly)")
    print(f"   Median HHI:  {conc['hhi'].median():.4f}")
    print(f"   Max HHI:     {conc['hhi'].max():.4f}  on {conc['hhi'].idxmax().date()}")
    print(f"   Mean top broker share: {conc['top_share'].mean():.2%}")
    print(f"   Most frequent top broker: {conc['top_broker'].mode().iloc[0]} "
          f"({(conc['top_broker'] == conc['top_broker'].mode().iloc[0]).sum()} days)")

    # 2. Persistence
    print(f"\n{'='*70}")
    print("2. BROKER RANKING PERSISTENCE (top-5 overlap next day)")
    print(f"{'='*70}")
    pers = broker_ranking_persistence(df, top_n=5)
    print(f"   Average overlap: {pers['avg_overlap']:.2%}")
    print(f"   Median overlap:  {pers['median_overlap']:.2%}")
    print(f"   Total day pairs: {pers['total_pairs']}")

    # 3. Top brokers all time
    print(f"\n{'='*70}")
    print("3. TOP BROKERS (all-time by total value)")
    print(f"{'='*70}")
    top = top_brokers_all_time(df)
    print(f"   {'Broker':<8} {'Total Value (Rp T)':>18} {'Active Days':>12} {'Avg Daily (Rp B)':>16}")
    print(f"   {'-'*56}")
    for broker, row in top.iterrows():
        print(f"   {broker:<8} {row['total_value']/1e12:>18.2f} {int(row['active_days']):>12} {row['avg_daily_value']/1e9:>16.2f}")

    # 4. Concentration vs volatility
    print(f"\n{'='*70}")
    print("4. CONCENTRATION vs IHSG VOLATILITY")
    print(f"{'='*70}")
    merged = concentration_vs_volatility(conc, storage)
    if merged is not None and len(merged) > 30:
        corr_hhi_vol = merged["hhi"].corr(merged["vol_20d"])
        corr_top_vol = merged["top_share"].corr(merged["vol_20d"])
        print(f"   Corr(HHI, 20d volatility):  {corr_hhi_vol:+.4f}")
        print(f"   Corr(top_share, volatility): {corr_top_vol:+.4f}")
        print(f"   Interpretation: {'higher concentration on volatile days' if corr_hhi_vol > 0 else 'lower concentration on volatile days'}")
    else:
        print("   Insufficient data for IHSG correlation")

    # Save
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    conc.to_csv(out_path)
    print(f"\nDaily concentration saved to: {out_path}")

    top_path = out_path.parent / "broker_top_alltime.csv"
    top.to_csv(top_path)
    print(f"Top brokers saved to: {top_path}")


if __name__ == "__main__":
    main()
