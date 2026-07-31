"""Google Trends Sentiment — search interest sebagai leading indicator.

Search volume naik 1-3 hari sebelum retail investor beli.
Gunakan pytrends API (gratis) untuk ambil data Google Trends.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("sentiment.google_trends")


class GoogleTrendsSentiment:
    """Compute sentiment from Google Trends search interest."""

    name = "google_trends"

    # Map ticker to search keywords
    SEARCH_KEYWORDS = {
        "BBCA.JK": ["saham BCA", "BBCA", "bank bca saham"],
        "TLKM.JK": ["saham Telkom", "TLKM", "telkom saham"],
        "ASII.JK": ["saham Astra", "ASII", "astra international saham"],
        "UNVR.JK": ["saham Unilever", "UNVR", "unilever indonesia saham"],
        "GGRM.JK": ["saham Gudang Garam", "GGRM"],
        "BMRI.JK": ["saham Mandiri", "BMRI", "bank mandiri saham"],
        "BBRI.JK": ["saham BRI", "BBRI", "bank bri saham"],
        "ICBP.JK": ["saham Indofood", "ICBP", "indofood cbp saham"],
        "ADRO.JK": ["saham Adaro", "ADRO"],
        "MDKA.JK": ["saham Merdeka", "MDKA", "merdeka copper"],
    }

    def __init__(self, storage=None):
        self.storage = storage

    def compute(self, ticker: str) -> dict | None:
        """Fetch Google Trends data and compute sentiment.

        Rising search interest = increasing retail attention (bullish for momentum).
        Falling search interest = waning interest (bearish for momentum).
        """
        try:
            from pytrends.request import TrendReq
        except ImportError:
            logger.debug("pytrends not installed, skipping Google Trends")
            return None

        keywords = self.SEARCH_KEYWORDS.get(ticker, [ticker.replace(".JK", "")])
        try:
            pytrends = TrendReq(hl="id-ID", tz=420)  # Indonesia locale, WIB timezone
            pytrends.build_payload(keywords, timeframe="today 3-m", geo="ID")
            interest_df = pytrends.interest_over_time()

            if interest_df.empty:
                return None

            # Use the first keyword column (or average if multiple)
            keyword_cols = [c for c in interest_df.columns if c != "isPartial"]
            if not keyword_cols:
                return None

            interest = interest_df[keyword_cols].mean(axis=1)

            # Trend: compare recent 7 days vs previous 7 days
            if len(interest) < 14:
                return None

            recent_avg = interest.iloc[-7:].mean()
            prev_avg = interest.iloc[-14:-7].mean()

            if prev_avg == 0:
                change_ratio = 1.0 if recent_avg > 0 else 0.0
            else:
                change_ratio = (recent_avg - prev_avg) / prev_avg

            # Normalize: >50% increase = strong bullish, >20% = bullish, etc.
            sentiment = max(-1, min(1, change_ratio * 2))  # Scale and clamp
            score = (sentiment + 1) * 50

            signal = (
                "rising_interest" if change_ratio > 0.2
                else "falling_interest" if change_ratio < -0.2
                else "stable_interest"
            )

            return {
                "score": round(float(score), 2),
                "sentiment": round(float(sentiment), 4),
                "signal": signal,
                "detail": {
                    "recent_avg_interest": round(float(recent_avg), 1),
                    "previous_avg_interest": round(float(prev_avg), 1),
                    "change_pct": round(float(change_ratio * 100), 1),
                    "keywords": keywords,
                },
            }

        except Exception as e:
            logger.debug(f"Google Trends error: {e}")
            return None
