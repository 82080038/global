"""Pre-compute all engine scores for each historical day — save to DB with as_of=date.

Arsitektur:
  1. Data OHLCV sudah di DB (dari Parquet archive)
  2. Script ini menjalankan SEMUA engine untuk setiap hari historis
  3. Skor disimpan ke tabel `scores` dengan as_of = tanggal_historis (bukan now())
  4. Replay cukup query: SELECT score FROM scores WHERE as_of <= ? ORDER BY as_of DESC LIMIT 1

Engine yang dijalankan per hari (semua point-in-time, no look-ahead):
  - Technical: RSI, MACD, MA, ADX, Bollinger (dari OHLCV filtered)
  - Fundamental: PE, PBV, ROE, DER (dari fundamental_data table, PER recompute with price)
  - Macro: US10Y, Gold, Oil, USD/IDR, DXY regime (dari OHLCV macro tickers filtered)
  - Global: S&P500, Nikkei, HangSeng, DAX, FTSE above MA50/MA200 (dari OHLCV global filtered)
  - Relationship: Rolling correlation with benchmark/macro/global (dari OHLCV filtered)
  - Sentiment: Foreign flow from DB + price momentum + volume ratio

Penggunaan:
    ./venv/bin/python scripts/precompute_scores.py [--tickers BBCA.JK,TLKM.JK]
                                                    [--months 12]
                                                    [--clean]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trading_system.analysis.fundamental import FundamentalAnalysisEngine
from trading_system.analysis.technical import TechnicalAnalysisEngine
from trading_system.config import DEFAULT_BENCHMARK, DEFAULT_GLOBAL_TICKERS, DEFAULT_MACRO_TICKERS
from trading_system.data.storage import DataStorage
from trading_system.analysis.relationship import MarketRelationshipEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("precompute")


class ScorePrecomputer:
    """Pre-compute all engine scores for each historical day, save to DB."""

    def __init__(self, storage: DataStorage | None = None):
        self.storage = storage or DataStorage()
        self.technical = TechnicalAnalysisEngine()
        self.fundamental = FundamentalAnalysisEngine()
        self.relationship = MarketRelationshipEngine(storage=self.storage)

    def _compute_technical(self, df_up_to: pd.DataFrame) -> tuple[float, dict]:
        """Technical score from point-in-time OHLCV."""
        if df_up_to.empty or len(df_up_to) < 14:
            return 50.0, {"reason": "insufficient_data"}
        self.technical.ohlcv = df_up_to
        result = self.technical.analyze()
        if result.get("status") == "ok":
            return float(result.get("score", 50.0)), result.get("breakdown", {})
        return 50.0, {"reason": result.get("status")}

    def _compute_fundamental(self, date: pd.Timestamp, df_up_to: pd.DataFrame) -> tuple[float, dict]:
        """Fundamental score from DB (fundamental_data table), point-in-time."""
        date_str = str(date.date())
        ratios = {}
        try:
            with self.storage._connect() as conn:
                row = conn.execute(
                    """SELECT pe_ratio, pb_ratio, roe, debt_to_equity, dividend_yield,
                              earnings_per_share, book_value_per_share, net_profit,
                              revenue, total_assets, total_liabilities, cash_flow
                       FROM fundamental_data
                       WHERE ticker = ? AND date <= ? AND pe_ratio IS NOT NULL
                       ORDER BY date DESC LIMIT 1""",
                    (self._ticker, date_str),
                ).fetchone()
                if row:
                    ratios = {
                        "PER": row[0], "PBV": row[1], "ROE": row[2], "DER": row[3],
                        "dividend_yield": row[4] or 0, "EPS": row[5], "BPS": row[6],
                    }
                    # Recalculate PER with current price
                    if ratios.get("EPS") and ratios["EPS"] > 0 and not df_up_to.empty:
                        last_price = float(df_up_to["close"].iloc[-1])
                        ratios["PER"] = last_price / ratios["EPS"]
        except Exception:
            pass

        if not ratios:
            return 50.0, {"reason": "no_fundamental_data"}

        score, breakdown, coverage = self.fundamental.compute_score(ratios)
        return float(score) if score else 50.0, breakdown

    def _compute_macro(self, date: pd.Timestamp) -> tuple[float, dict]:
        """Macro score from macro tickers (US10Y, Gold, Oil, USD/IDR, DXY), point-in-time."""
        rates = {}
        for label, ticker in DEFAULT_MACRO_TICKERS.items():
            df = self.storage.load_ohlcv(ticker)
            if df.empty:
                rates[label] = None
                continue
            df = df[df.index <= date]
            if df.empty or len(df) < 2:
                rates[label] = None
                continue
            last = df.iloc[-1]
            prev = df.iloc[-20] if len(df) >= 20 else df.iloc[0]
            rates[label] = (float(last["close"]), float(prev["close"]))

        # Classify regime
        try:
            us10y_now, _ = rates.get("US10Y") or (None, None)
            gold_now, _ = rates.get("GOLD") or (None, None)
            oil_now, _ = rates.get("OIL") or (None, None)
            usd_idr_now, _ = rates.get("USD_IDR") or (None, None)

            if us10y_now is None:
                regime = "unknown"
            elif us10y_now > 4.5 and (gold_now is None or gold_now < 2000):
                regime = "tightening"
            elif us10y_now < 3.5 and (gold_now is None or gold_now > 2000):
                regime = "easing"
            elif oil_now and usd_idr_now and oil_now > 80 and usd_idr_now < 16000:
                regime = "growth"
            elif oil_now and usd_idr_now and oil_now < 70 and usd_idr_now > 16000:
                regime = "slowdown"
            else:
                regime = "neutral"
        except Exception:
            regime = "neutral"

        # Score: easing/growth = bullish, tightening/slowdown = bearish
        regime_scores = {
            "easing": 70, "growth": 65, "neutral": 50,
            "tightening": 35, "slowdown": 30, "unknown": 50,
        }
        score = regime_scores.get(regime, 50)
        breakdown = {"regime": regime, "rates": {k: v[0] if v else None for k, v in rates.items()}}
        return float(score), breakdown

    def _compute_global(self, date: pd.Timestamp) -> tuple[float, dict]:
        """Global market score from global indices, point-in-time."""
        above_50ma = 0
        above_200ma = 0
        total = 0

        for label, ticker in DEFAULT_GLOBAL_TICKERS.items():
            df = self.storage.load_ohlcv(ticker)
            if df.empty:
                continue
            df = df[df.index <= date].copy()
            if df.empty:
                continue
            df["ma_50"] = df["close"].rolling(50).mean()
            df["ma_200"] = df["close"].rolling(200).mean()
            last = df.iloc[-1]
            total += 1
            if not pd.isna(last.get("ma_50")) and last["close"] > last["ma_50"]:
                above_50ma += 1
            if not pd.isna(last.get("ma_200")) and last["close"] > last["ma_200"]:
                above_200ma += 1

        if total == 0:
            return 50.0, {"global_above_50ma": 0, "global_above_200ma": 0}

        score = (above_50ma / total) * 50 + (above_200ma / total) * 50
        return float(score), {"above_50ma": above_50ma, "above_200ma": above_200ma, "total": total}

    def _compute_relationship(self, date: pd.Timestamp, ticker: str) -> tuple[float, dict]:
        """Relationship score — rolling correlation with benchmark, point-in-time."""
        df_a = self.storage.load_ohlcv(ticker)
        if df_a.empty:
            return 50.0, {"reason": "no_data"}
        df_a = df_a[df_a.index <= date]
        if len(df_a) < 60:
            return 50.0, {"reason": "insufficient_data"}

        returns_a = df_a["close"].pct_change().dropna()
        rels = []
        for label, other in {**DEFAULT_GLOBAL_TICKERS, **DEFAULT_MACRO_TICKERS, "IHSG": DEFAULT_BENCHMARK}.items():
            df_b = self.storage.load_ohlcv(other)
            if df_b.empty:
                continue
            df_b = df_b[df_b.index <= date]
            if len(df_b) < 60:
                continue
            returns_b = df_b["close"].pct_change().dropna()
            common = returns_a.index.intersection(returns_b.index)
            if len(common) < 30:
                continue
            x = returns_a.loc[common].iloc[-60:]
            y = returns_b.loc[common].iloc[-60:]
            corr = x.corr(y)
            if not np.isnan(corr):
                rels.append({"asset": label, "correlation": float(corr)})

        if not rels:
            return 50.0, {"reason": "no_relationships"}

        # Score: positive correlation with IHSG is good, negative is bad
        bench_corr = 0
        for r in rels:
            if r["asset"] == "IHSG":
                bench_corr = r["correlation"]
                break
        score = 50 + bench_corr * 30
        score = max(0, min(100, score))
        return float(score), {"relationships": rels, "bench_corr": bench_corr}

    def _compute_sentiment(self, date: pd.Timestamp, df_up_to: pd.DataFrame, ticker: str) -> tuple[float, dict]:
        """Sentiment from foreign_flow DB + price momentum + volume ratio."""
        components = []

        # 1. Foreign flow from DB
        date_str = str(date.date())
        try:
            with self.storage._connect() as conn:
                rows = conn.execute(
                    """SELECT foreign_net FROM foreign_flow
                       WHERE ticker = ? AND date <= ?
                       ORDER BY date DESC LIMIT 20""",
                    (ticker, date_str),
                ).fetchall()
                if rows:
                    nets = [r[0] for r in rows if r[0] is not None]
                    if nets:
                        avg_net = sum(nets) / len(nets)
                        flow_score = max(-20, min(20, avg_net / 1e9 * 2))
                        components.append(("foreign_flow", flow_score, 0.4))
        except Exception:
            pass

        # 2. Price momentum
        if len(df_up_to) >= 20:
            ret_5d = float(df_up_to["close"].iloc[-1] / df_up_to["close"].iloc[-5] - 1) if len(df_up_to) >= 5 else 0
            ret_20d = float(df_up_to["close"].iloc[-1] / df_up_to["close"].iloc[-20] - 1) if len(df_up_to) >= 20 else 0
            momentum_score = max(-30, min(30, ret_5d * 200 + ret_20d * 100))
            components.append(("momentum", momentum_score, 0.35))

        # 3. Volume ratio
        if len(df_up_to) >= 20:
            vol_recent = float(df_up_to["volume"].iloc[-5:].mean())
            vol_avg = float(df_up_to["volume"].iloc[-20:].mean())
            if vol_avg > 0:
                vol_score = max(-10, min(10, (vol_recent / vol_avg - 1) * 15))
                components.append(("volume", vol_score, 0.25))

        if not components:
            return 50.0, {"reason": "no_data"}

        total_weight = sum(w for _, _, w in components)
        score = 50 + sum(s * w for _, s, w in components) / total_weight
        score = max(0, min(100, score))
        return float(score), {"components": [c[0] for c in components]}

    def _save_score(self, ticker: str, engine: str, score: float, breakdown: dict, as_of: str):
        """Save score to DB with historical as_of date."""
        with self.storage._connect() as conn:
            conn.execute(
                "INSERT INTO scores (ticker, engine, score, breakdown, as_of) VALUES (?, ?, ?, ?, ?)",
                (ticker, engine, round(score, 2), json.dumps(breakdown, default=str), as_of),
            )
            conn.commit()

    def _clean_old_scores(self, ticker: str):
        """Clean old pre-computed scores for this ticker."""
        with self.storage._connect() as conn:
            # Delete scores where as_of is a date string (YYYY-MM-DD), not ISO timestamp
            # Pre-computed scores use date format, pipeline scores use ISO format
            conn.execute(
                """DELETE FROM scores WHERE ticker = ? AND as_of NOT LIKE '%T%'""",
                (ticker,),
            )
            conn.commit()
        logger.info(f"  Cleaned old pre-computed scores for {ticker}")

    def precompute(self, ticker: str, months: int = 12, clean: bool = False) -> int:
        """Pre-compute all scores for each historical day."""
        self._ticker = ticker

        if clean:
            self._clean_old_scores(ticker)

        # Load full OHLCV
        full_df = self.storage.load_ohlcv(ticker)
        if full_df.empty:
            logger.warning(f"No OHLCV for {ticker}")
            return 0

        # Calculate replay period
        end_date = full_df.index[-1]
        start_date = end_date - timedelta(days=months * 30)
        replay_days = full_df[full_df.index >= start_date].index

        logger.info(f"Pre-computing scores for {ticker}: {replay_days[0].date()} → {replay_days[-1].date()} ({len(replay_days)} days)")

        count = 0
        for i, date in enumerate(replay_days):
            df_up_to = full_df[full_df.index <= date].copy()
            if len(df_up_to) < 50:
                continue

            date_str = str(date.date())

            # Compute all scores
            tech_score, tech_breakdown = self._compute_technical(df_up_to)
            fund_score, fund_breakdown = self._compute_fundamental(date, df_up_to)
            macro_score, macro_breakdown = self._compute_macro(date)
            global_score, global_breakdown = self._compute_global(date)
            rel_score, rel_breakdown = self._compute_relationship(date, ticker)
            sent_score, sent_breakdown = self._compute_sentiment(date, df_up_to, ticker)

            # Save to DB with historical date
            self._save_score(ticker, "technical", tech_score, tech_breakdown, date_str)
            self._save_score(ticker, "fundamental", fund_score, fund_breakdown, date_str)
            self._save_score(ticker, "macro", macro_score, macro_breakdown, date_str)
            self._save_score(ticker, "global", global_score, global_breakdown, date_str)
            self._save_score(ticker, "relationship", rel_score, rel_breakdown, date_str)
            self._save_score(ticker, "sentiment", sent_score, sent_breakdown, date_str)

            count += 1
            if (i + 1) % 50 == 0 or i == 0 or i == len(replay_days) - 1:
                logger.info(
                    f"  [{date.date()}] Day {i+1}/{len(replay_days)} | "
                    f"tech={tech_score:.1f} fund={fund_score:.1f} macro={macro_score:.1f} "
                    f"global={global_score:.1f} rel={rel_score:.1f} sent={sent_score:.1f}"
                )

        logger.info(f"  Done: {count} days × 6 engines = {count * 6} scores saved")
        return count


def main():
    parser = argparse.ArgumentParser(description="Pre-compute all engine scores for historical days")
    parser.add_argument("--tickers", default="BBCA.JK,TLKM.JK,ASII.JK,BMRI.JK,GOTO.JK,UNVR.JK",
                        help="Comma-separated tickers")
    parser.add_argument("--months", type=int, default=12, help="How many months back to compute")
    parser.add_argument("--clean", action="store_true", help="Clean old pre-computed scores first")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",")]
    pc = ScorePrecomputer()

    total = 0
    for ticker in tickers:
        logger.info(f"\n{'='*60}")
        logger.info(f"  Pre-computing: {ticker}")
        logger.info(f"{'='*60}")
        count = pc.precompute(ticker, months=args.months, clean=args.clean)
        total += count

    logger.info(f"\n{'='*60}")
    logger.info(f"  TOTAL: {total} days × 6 engines = {total * 6} scores saved")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    main()
