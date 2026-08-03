"""Foreign Net Flow Sentiment — ambil data foreign buy/sell dari IDX.

Foreign investor adalah driver utama di Bursa Efek Indonesia.
Net buy = bullish signal, net sell = bearish signal.

Data source (prioritas):
1. Tabel `foreign_flow` di SQLite dengan source='idx_scraper' (data riil IDX, 2020+)
2. Fallback ke proxy OHLCV+volume jika data riil tidak tersedia
   (untuk ticker di luar 47 blue chips atau periode sebelum 2020).

Backup data riil ke Parquet dilakukan oleh `data/idx_batch.py` saat scrape.
Lihat: E:/trading_data/archive/foreign_flow_idx/
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger("sentiment.foreign_flow")


class ForeignFlowSentiment:
    """Compute sentiment from foreign net flow patterns.

    Primary source: real IDX foreign flow data from `foreign_flow` table
    (scraped by `data/idx_batch.py` from idx.co.id getStockSummary).

    Fallback: proxy from OHLCV + volume patterns when real data unavailable.
    """

    name = "foreign_flow"

    def __init__(self, storage=None):
        self.storage = storage

    def _ticker_code(self, ticker: str) -> str:
        """Strip .JK suffix untuk matching dengan tabel foreign_flow."""
        return ticker.replace(".JK", "").replace(".JK", "").strip()

    def _load_real_foreign_flow(self, ticker: str, lookback: int = 60) -> pd.DataFrame | None:
        """Load real foreign flow data dari tabel foreign_flow (source='idx_scraper').

        Returns DataFrame dengan index date dan kolom foreign_net, foreign_buy,
        foreign_sell, atau None jika tidak ada data.
        """
        if self.storage is None:
            return None
        try:
            code = self._ticker_code(ticker)
            df = self.storage.load_foreign_flow(code, source="idx_scraper")
            if df.empty:
                return None
            df = df.copy()
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").set_index("date")
            if len(df) > lookback:
                df = df.iloc[-lookback:]
            return df
        except Exception as e:
            logger.debug(f"Failed to load real foreign flow for {ticker}: {e}")
            return None

    def _compute_real(self, ff: pd.DataFrame) -> dict | None:
        """Compute sentiment from real IDX foreign flow data.

        Logic:
        1. Hitung net flow ratio = foreign_net / (foreign_buy + foreign_sell)
        2. Recent 5-bar momentum: rata-rata foreign_net terakhir
        3. Persistence: berapa % hari terakhir yang net buy
        4. Combine: 50% net ratio + 30% momentum + 20% persistence
        """
        if ff.empty or len(ff) < 5:
            return None

        recent = ff.iloc[-20:] if len(ff) >= 20 else ff

        # Net flow ratio (-1 to 1)
        total_buy = recent["foreign_buy"].sum()
        total_sell = recent["foreign_sell"].sum()
        total = total_buy + total_sell
        if total > 0:
            net_ratio = (total_buy - total_sell) / total
        else:
            net_ratio = 0.0

        # Recent 5-bar momentum (scaled)
        last5 = ff.iloc[-5:]
        avg_net = last5["foreign_net"].mean()
        # Normalize by typical daily flow magnitude
        typical_magnitude = recent["foreign_buy"].mean() + recent["foreign_sell"].mean()
        if typical_magnitude > 0:
            momentum = max(-1, min(1, avg_net / (typical_magnitude / 2)))
        else:
            momentum = 0.0

        # Persistence: % of last 10 bars that are net buy
        last10 = ff.iloc[-10:] if len(ff) >= 10 else ff
        persistence = (last10["foreign_net"] > 0).sum() / len(last10)
        persistence_score = (persistence - 0.5) * 2  # -1 to 1

        # Combine
        combined = 0.5 * net_ratio + 0.3 * momentum + 0.2 * persistence_score
        combined = max(-1, min(1, combined))
        score = (combined + 1) * 50  # 0..100

        if combined > 0.15:
            signal = "foreign_accumulation"
        elif combined < -0.15:
            signal = "foreign_distribution"
        else:
            signal = "neutral"

        return {
            "score": round(float(score), 2),
            "sentiment": round(float(combined), 4),
            "signal": signal,
            "source": "idx_real",
            "detail": {
                "net_flow_ratio": round(float(net_ratio), 4),
                "recent_momentum": round(float(momentum), 4),
                "persistence": round(float(persistence), 4),
                "total_foreign_buy": int(total_buy),
                "total_foreign_sell": int(total_sell),
                "net_foreign_flow": int(total_buy - total_sell),
                "days_positive": int((last10["foreign_net"] > 0).sum()),
                "days_total": int(len(last10)),
                "data_source": "idx_scraper",
            },
        }

    def _compute_proxy(self, ticker: str) -> dict | None:
        """Fallback: proxy from OHLCV + volume patterns (original logic).

        Proxy: large volume bars with price up = foreign accumulation,
        large volume bars with price down = foreign distribution.
        """
        if self.storage is None:
            return None

        df = self.storage.load_ohlcv(ticker, limit=60)
        if df.empty or len(df) < 20:
            return None

        df = df.copy()
        df["returns"] = df["close"].pct_change()
        df["vol_ma"] = df["volume"].rolling(20).mean()
        df["vol_ratio"] = df["volume"] / df["vol_ma"]

        high_vol = df[df["vol_ratio"] > 1.5].dropna()

        if high_vol.empty:
            return {
                "score": 50.0,
                "sentiment": 0.0,
                "signal": "neutral",
                "source": "proxy",
                "detail": "No significant volume spikes detected",
            }

        accumulation = high_vol[high_vol["returns"] > 0]
        distribution = high_vol[high_vol["returns"] < 0]

        acc_vol = accumulation["volume"].sum()
        dist_vol = distribution["volume"].sum()
        total_vol = acc_vol + dist_vol

        if total_vol == 0:
            net_ratio = 0.0
        else:
            net_ratio = (acc_vol - dist_vol) / total_vol

        recent = df.iloc[-5:]
        recent_flow = recent["returns"].mean() * recent["vol_ratio"].mean()

        combined = 0.7 * net_ratio + 0.3 * max(-1, min(1, recent_flow * 10))
        score = (combined + 1) * 50

        signal = "foreign_accumulation" if combined > 0.15 else "foreign_distribution" if combined < -0.15 else "neutral"

        return {
            "score": round(float(score), 2),
            "sentiment": round(float(combined), 4),
            "signal": signal,
            "source": "proxy",
            "detail": {
                "accumulation_volume": int(acc_vol),
                "distribution_volume": int(dist_vol),
                "net_ratio": round(float(net_ratio), 4),
                "high_vol_bars": len(high_vol),
                "data_source": "ohlcv_proxy",
            },
        }

    def compute(self, ticker: str) -> dict | None:
        """Analyze foreign flow sentiment.

        Priority: real IDX data → proxy fallback.
        """
        # Try real IDX foreign flow data first
        ff = self._load_real_foreign_flow(ticker)
        if ff is not None and not ff.empty:
            result = self._compute_real(ff)
            if result is not None:
                return result

        # Fallback to proxy
        return self._compute_proxy(ticker)
