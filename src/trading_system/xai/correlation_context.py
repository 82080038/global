"""Correlation Context Provider untuk XAI.

Menyediakan konteks hubungan dan pola data untuk narasi penjelasan:
- Foreign flow: akumulasi/distribusi asing + persistence
- Lead-lag: saham leader/follower vs ticker lain
- Broker concentration: HHI pasar + dominasi broker
- Korelasi foreign flow vs forward return (prediksi arah)

Data bersumber dari tabel foreign_flow, broker_flow, dan ohlcv
yang diisi oleh idx_batch.py (data riil IDX 2020+).
"""

from __future__ import annotations

import logging
from datetime import timedelta

import numpy as np
import pandas as pd

from trading_system.data.storage import DataStorage

logger = logging.getLogger("xai.correlation_context")


# Saham yang dianalisis lead-lag (sesuai dry_run_lead_lag.py default)
LEAD_LAG_UNIVERSE = [
    "BBCA.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "ASII.JK", "UNVR.JK",
    "ANTM.JK", "ICBP.JK", "GGRM.JK", "KLBF.JK", "CPIN.JK", "ADRO.JK",
    "PTBA.JK", "MDKA.JK", "MEDC.JK", "PGAS.JK", "INCO.JK", "TINS.JK",
    "INDF.JK", "MYOR.JK",
]

FORWARD_HORIZONS = [1, 3, 5, 10]


class CorrelationContextProvider:
    """Provide correlation/flow/lead-lag context untuk XAI narrative."""

    def __init__(self, storage: DataStorage | None = None):
        self.storage = storage or DataStorage()
        self._ff_cache: dict[str, pd.DataFrame] = {}
        self._lead_lag_cache: dict[str, list[dict]] | None = None

    def _ticker_code(self, ticker: str) -> str:
        return ticker.replace(".JK", "").strip()

    # ---------- Foreign Flow Context ----------

    def _load_foreign_flow(self, ticker: str, lookback: int = 20) -> pd.DataFrame | None:
        code = self._ticker_code(ticker)
        if code in self._ff_cache:
            df = self._ff_cache[code]
            if len(df) >= lookback:
                return df.iloc[-lookback:]

        try:
            df = self.storage.load_foreign_flow(code, source="idx_scraper")
        except Exception:
            return None
        if df.empty:
            return None
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").set_index("date")
        self._ff_cache[code] = df
        return df.iloc[-lookback:] if len(df) >= lookback else df

    def get_foreign_flow_context(self, ticker: str) -> dict:
        """Konteks foreign flow untuk ticker: arah, kekuatan, persistence."""
        ff = self._load_foreign_flow(ticker)
        if ff is None or ff.empty or len(ff) < 5:
            return {"available": False}

        recent = ff.iloc[-20:] if len(ff) >= 20 else ff
        total_buy = recent["foreign_buy"].sum()
        total_sell = recent["foreign_sell"].sum()
        net = total_buy - total_sell
        total = total_buy + total_sell
        net_ratio = net / total if total > 0 else 0.0

        last10 = ff.iloc[-10:] if len(ff) >= 10 else ff
        days_positive = int((last10["foreign_net"] > 0).sum())
        persistence = days_positive / len(last10)

        # Trend: 5-day vs previous 5-day
        if len(ff) >= 10:
            recent5_net = ff.iloc[-5:]["foreign_net"].sum()
            prev5_net = ff.iloc[-10:-5]["foreign_net"].sum()
            trend = "increasing" if recent5_net > prev5_net else "decreasing"
        else:
            trend = "unknown"

        if net_ratio > 0.15 and persistence > 0.6:
            phase = "strong_accumulation"
        elif net_ratio > 0.05:
            phase = "accumulation"
        elif net_ratio < -0.15 and persistence < 0.4:
            phase = "strong_distribution"
        elif net_ratio < -0.05:
            phase = "distribution"
        else:
            phase = "neutral"

        return {
            "available": True,
            "phase": phase,
            "net_ratio": round(net_ratio, 4),
            "persistence": round(persistence, 4),
            "trend": trend,
            "total_buy": int(total_buy),
            "total_sell": int(total_sell),
            "net_flow": int(net),
            "days_positive_10d": days_positive,
            "days_total_10d": len(last10),
        }

    # ---------- Foreign Flow vs Return Correlation ----------

    def get_flow_return_correlation(self, ticker: str) -> dict:
        """Korelasi foreign net flow vs forward return untuk ticker."""
        code = self._ticker_code(ticker)
        ff = self._load_foreign_flow(code, lookback=9999)
        if ff is None or len(ff) < 60:
            return {"available": False}

        ohlcv = self.storage.load_ohlcv(f"{code}.JK")
        if ohlcv.empty:
            return {"available": False}
        ohlcv = ohlcv.copy()
        ohlcv.index = pd.to_datetime(ohlcv.index).tz_localize(None)
        ohlcv = ohlcv[~ohlcv.index.duplicated(keep="last")]

        df = ff.join(ohlcv[["close"]], how="inner")
        if len(df) < 60:
            return {"available": False}

        corrs = {}
        for h in FORWARD_HORIZONS:
            df[f"ret_{h}d"] = df["close"].pct_change(h).shift(-h)
            valid = df[["foreign_net", f"ret_{h}d"]].dropna()
            if len(valid) >= 30:
                corrs[h] = round(float(valid["foreign_net"].corr(valid[f"ret_{h}d"])), 4)
            else:
                corrs[h] = None

        # Interpretasi: korelasi negatif = kontra-indikator
        best_h = 5
        best_corr = corrs.get(best_h)
        if best_corr is not None:
            if best_corr < -0.05:
                predictive = "contrarian"
                meaning = "foreign buy cenderung diikuti harga turun"
            elif best_corr > 0.05:
                predictive = "confirming"
                meaning = "foreign buy cenderung diikuti harga naik"
            else:
                predictive = "neutral"
                meaning = "foreign flow tidak punya daya prediksi signifikan"
        else:
            predictive = "unknown"
            meaning = "data tidak cukup"

        return {
            "available": True,
            "correlations": corrs,
            "best_horizon": best_h,
            "best_corr": best_corr,
            "predictive_type": predictive,
            "meaning": meaning,
        }

    # ---------- Lead-Lag Context ----------

    def _compute_lead_lag(self) -> dict[str, list[dict]]:
        """Compute lead-lag untuk semua pasangan di universe (cached)."""
        if self._lead_lag_cache is not None:
            return self._lead_lag_cache

        from trading_system.analysis.lead_lag import LeadLagAnalyzer

        returns_data = {}
        for t in LEAD_LAG_UNIVERSE:
            df = self.storage.load_ohlcv(t)
            if df.empty or len(df) < 200:
                continue
            df = df.sort_index()
            closes = df["close"].values.astype(float)
            rets = np.diff(closes) / closes[:-1]
            returns_data[t] = np.nan_to_num(rets, nan=0.0)

        if len(returns_data) < 2:
            self._lead_lag_cache = {}
            return self._lead_lag_cache

        analyzer = LeadLagAnalyzer(max_offset=10, min_bars=200, corr_threshold=0.3)
        from itertools import combinations

        pairs = list(combinations(returns_data.keys(), 2))
        results = analyzer.analyze_multiple(returns_data, pairs)

        cache: dict[str, list[dict]] = {}
        for r in results:
            leader = r["leader"]
            follower = r["follower"]
            if r.get("significant") and r["direction"] != "synchronous":
                cache.setdefault(leader, []).append(r)
                cache.setdefault(follower, []).append(r)

        self._lead_lag_cache = cache
        return cache

    def get_lead_lag_context(self, ticker: str) -> dict:
        """Konteks lead-lag: ticker ini leader atau follower? Untuk siapa?"""
        ll = self._compute_lead_lag()
        if not ll or ticker not in ll:
            return {"available": False, "is_leader": False, "is_follower": False}

        entries = ll[ticker]
        leads = []
        follows = []

        for r in entries:
            if r["direction"] == "leader_leads" and r["leader"] == ticker:
                leads.append({
                    "follower": r["follower"],
                    "offset": r["best_offset"],
                    "corr": r["best_corr"],
                })
            elif r["direction"] == "follower_leads" and r["follower"] == ticker:
                follows.append({
                    "leader": r["leader"],
                    "offset": r["best_offset"],
                    "corr": r["best_corr"],
                })
            elif r["direction"] == "follower_leads" and r["leader"] == ticker:
                # ticker is follower
                follows.append({
                    "leader": r["follower"],
                    "offset": abs(r["best_offset"]),
                    "corr": r["best_corr"],
                })
            elif r["direction"] == "leader_leads" and r["follower"] == ticker:
                leads.append({
                    "follower": r["leader"],
                    "offset": abs(r["best_offset"]),
                    "corr": r["best_corr"],
                })

        leads.sort(key=lambda x: abs(x["corr"]), reverse=True)
        follows.sort(key=lambda x: abs(x["corr"]), reverse=True)

        return {
            "available": True,
            "is_leader": len(leads) > 0,
            "is_follower": len(follows) > 0,
            "leads": leads[:5],
            "follows": follows[:5],
        }

    # ---------- Broker Concentration Context ----------

    def get_broker_context(self) -> dict:
        """Konteks broker concentration pasar (ringkasan terbaru)."""
        try:
            df = self.storage.load_broker_flow(source="idx_scraper")
        except Exception:
            return {"available": False}
        if df.empty:
            return {"available": False}

        # Ambil 30 hari terakhir
        df["date"] = pd.to_datetime(df["date"])
        latest_date = df["date"].max()
        recent = df[df["date"] >= latest_date - timedelta(days=30)]
        if recent.empty:
            return {"available": False}

        # Top broker terakhir
        latest_day = recent[recent["date"] == latest_date]
        if latest_day.empty:
            return {"available": False}

        top_broker = latest_day.loc[latest_day["net_value"].idxmax(), "broker"]
        top_share = latest_day["net_value"].max() / latest_day["net_value"].sum()

        # HHI
        values = recent.groupby("broker")["net_value"].sum().values
        total = values.sum()
        if total > 0:
            hhi = float(((values / total) ** 2).sum())
        else:
            hhi = 0.0

        return {
            "available": True,
            "latest_date": latest_date.strftime("%Y-%m-%d"),
            "top_broker": top_broker,
            "top_share": round(top_share, 4),
            "hhi_30d": round(hhi, 4),
            "n_active_brokers": recent["broker"].nunique(),
        }

    # ---------- Combined Context ----------

    def get_full_context(self, ticker: str) -> dict:
        """Gabungkan semua konteks untuk XAI narrative."""
        return {
            "foreign_flow": self.get_foreign_flow_context(ticker),
            "flow_return_corr": self.get_flow_return_correlation(ticker),
            "lead_lag": self.get_lead_lag_context(ticker),
            "broker": self.get_broker_context(),
        }
