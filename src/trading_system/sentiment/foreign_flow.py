"""Foreign Net Flow Sentiment — ambil data foreign buy/sell dari IDX.

Foreign investor adalah driver utama di Bursa Efek Indonesia.
Net buy = bullish signal, net sell = bearish signal.

Data source: Yahoo Finance institutional holders + price action proxy
(untuk foreign flow real-time, bisa di-upgrade ke IDX RSS atau API broker).
"""

from __future__ import annotations

import logging

logger = logging.getLogger("sentiment.foreign_flow")


class ForeignFlowSentiment:
    """Compute sentiment from foreign net flow patterns."""

    name = "foreign_flow"

    def __init__(self, storage=None):
        self.storage = storage

    def compute(self, ticker: str) -> dict | None:
        """Analyze foreign flow from OHLCV + volume patterns.

        Proxy: large volume bars with price up = foreign accumulation,
        large volume bars with price down = foreign distribution.
        (True foreign flow data requires IDX broker summary — see BrokerSummarySentiment)
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

        # High volume bars = institutional activity
        high_vol = df[df["vol_ratio"] > 1.5].dropna()

        if high_vol.empty:
            return {
                "score": 50.0,
                "sentiment": 0.0,
                "signal": "neutral",
                "detail": "No significant volume spikes detected",
            }

        # Accumulation: high volume + positive return
        accumulation = high_vol[high_vol["returns"] > 0]
        distribution = high_vol[high_vol["returns"] < 0]

        acc_vol = accumulation["volume"].sum()
        dist_vol = distribution["volume"].sum()
        total_vol = acc_vol + dist_vol

        if total_vol == 0:
            net_ratio = 0.0
        else:
            net_ratio = (acc_vol - dist_vol) / total_vol  # -1 to 1

        # Recent 5 bars momentum (more weight on recent)
        recent = df.iloc[-5:]
        recent_flow = recent["returns"].mean() * recent["vol_ratio"].mean()

        # Combine: 70% volume pattern + 30% recent momentum
        combined = 0.7 * net_ratio + 0.3 * max(-1, min(1, recent_flow * 10))
        score = (combined + 1) * 50  # 0..100

        signal = "foreign_accumulation" if combined > 0.15 else "foreign_distribution" if combined < -0.15 else "neutral"

        return {
            "score": round(float(score), 2),
            "sentiment": round(float(combined), 4),
            "signal": signal,
            "detail": {
                "accumulation_volume": int(acc_vol),
                "distribution_volume": int(dist_vol),
                "net_ratio": round(float(net_ratio), 4),
                "high_vol_bars": len(high_vol),
            },
        }
