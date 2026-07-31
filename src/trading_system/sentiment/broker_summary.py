"""Broker Summary Sentiment — track smart money dari IDX broker summary.

IDX publish broker summary harian: top buyer & top seller per ticker.
Broker asing besar (CLSA, Credit Suisse, JP Morgan, UBS) = "smart money".
Jika smart money net buy = bullish, net sell = bearish.

Data source: idx.co.id broker summary atau API pihak ketiga.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("sentiment.broker_summary")


# Smart money brokers (foreign + large institutional)
SMART_MONEY_BROKERS = {
    # Foreign brokers
    "CLSA", "CS", "JPM", "UBS", "MS", "GS", "DB", "CITI", "BNP", "BARCAP",
    "MACQ", "NOMURA", "MORGAN", "CREDIT", "SOCIATE",
    # Large local brokers with institutional clients
    "BNI", "BCA", "MANDIRI", "BRI", "CIMB", "MAYBANK", "BDO",
    "TRIMEGAH", "EVERGREEN", "MIRAE", "NHKORINDO", "DAIHACHI",
}

# Brokers that are known to be contrarian / retail
RETAIL_BROKERS = {
    "POIN", "IPOT", "STOCK", "MINNA", "MULIA", "PHILLIP",
}


class BrokerSummarySentiment:
    """Compute sentiment from broker summary data (smart money tracking)."""

    name = "broker_summary"

    def __init__(self, storage=None):
        self.storage = storage

    def _fetch_broker_summary(self, ticker: str) -> list[dict] | None:
        """Fetch broker summary from IDX public API.

        IDX exposes broker summary at:
        https://www.idx.co.id/primary/BrokerSummary/GetBrokers?ticker={code}&date={YYYYMMDD}

        Returns list of {broker, buy_volume, sell_volume, buy_value, sell_value}.
        Falls back to yfinance institutional holders if IDX API unavailable.
        """
        try:
            import requests
            from datetime import datetime

            ticker_code = ticker.replace(".JK", "")
            today = datetime.now().strftime("%Y%m%d")

            # IDX public API — broker summary for latest trading day
            url = f"https://www.idx.co.id/primary/BrokerSummary/GetBrokers"
            params = {"ticker": ticker_code, "date": today}

            resp = requests.get(url, params=params, timeout=10, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://www.idx.co.id/",
            })
            if resp.status_code != 200:
                logger.debug(f"IDX API returned {resp.status_code} for {ticker}")
                return self._fetch_yfinance_institutional(ticker)

            data = resp.json()
            if not data:
                return self._fetch_yfinance_institutional(ticker)

            # IDX API returns list of broker records
            brokers = []
            for item in data:
                brokers.append({
                    "broker": item.get("broker", item.get("code", "")),
                    "buy_volume": float(item.get("buyVolume", item.get("buyVolume1Lot", 0))),
                    "sell_volume": float(item.get("sellVolume", item.get("sellVolume1Lot", 0))),
                    "buy_value": float(item.get("buyValue", 0)),
                    "sell_value": float(item.get("sellValue", 0)),
                })
            return brokers if brokers else None

        except Exception as e:
            logger.debug(f"Broker summary fetch error: {e}")
            return self._fetch_yfinance_institutional(ticker)

    def _fetch_yfinance_institutional(self, ticker: str) -> list[dict] | None:
        """Fallback: use yfinance institutional holders as proxy for smart money.

        This is less granular than broker summary but provides directional signal
        from institutional ownership changes.
        """
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            holders = t.institutional_holders
            if holders is None or holders.empty:
                return None

            # Treat top institutional holders as smart money proxy
            brokers = []
            for _, row in holders.head(10).iterrows():
                broker_name = str(row.get("Holder", ""))
                shares = float(row.get("Shares", 0))
                pct = float(row.get("% Out", 0)) if "%" in row else 0
                # Use shares as proxy for buy_value, 0 for sell
                brokers.append({
                    "broker": broker_name[:10].upper(),
                    "buy_volume": shares,
                    "sell_volume": 0,
                    "buy_value": shares,
                    "sell_value": 0,
                })
            return brokers if brokers else None
        except Exception as e:
            logger.debug(f"yfinance institutional fallback error: {e}")
            return None

    def compute(self, ticker: str) -> dict | None:
        """Analyze smart money flow from broker summary.

        Logic:
        1. Fetch broker summary for today
        2. Identify smart money brokers (foreign + large institutional)
        3. Compute net buy/sell from smart money
        4. Compare with retail brokers (contrarian signal)
        """
        brokers = self._fetch_broker_summary(ticker)
        if not brokers:
            return None

        # Split into smart money vs retail vs other
        smart_buy_value = sum(b["buy_value"] for b in brokers if b["broker"] in SMART_MONEY_BROKERS)
        smart_sell_value = sum(b["sell_value"] for b in brokers if b["broker"] in SMART_MONEY_BROKERS)
        retail_buy_value = sum(b["buy_value"] for b in brokers if b["broker"] in RETAIL_BROKERS)
        retail_sell_value = sum(b["sell_value"] for b in brokers if b["broker"] in RETAIL_BROKERS)

        smart_net = smart_buy_value - smart_sell_value
        retail_net = retail_buy_value - retail_sell_value

        # Smart money net buy = bullish
        # Retail net buy while smart money sells = bearish (retail trap)
        total_smart = smart_buy_value + smart_sell_value
        if total_smart > 0:
            smart_ratio = smart_net / total_smart  # -1 to 1
        else:
            smart_ratio = 0.0

        # Retail contrarian: if retail buying heavily but smart money selling = bearish
        total_retail = retail_buy_value + retail_sell_value
        if total_retail > 0:
            retail_ratio = retail_net / total_retail
        else:
            retail_ratio = 0.0

        # Combined: 70% smart money + 30% retail contrarian
        combined = 0.7 * smart_ratio - 0.3 * retail_ratio  # retail contrarian (subtract)
        combined = max(-1, min(1, combined))
        score = (combined + 1) * 50

        signal = (
            "smart_money_accumulation" if combined > 0.1
            else "smart_money_distribution" if combined < -0.1
            else "neutral"
        )

        return {
            "score": round(float(score), 2),
            "sentiment": round(float(combined), 4),
            "signal": signal,
            "detail": {
                "smart_money_net": int(smart_net),
                "smart_money_buy": int(smart_buy_value),
                "smart_money_sell": int(smart_sell_value),
                "retail_net": int(retail_net),
                "smart_money_brokers_active": sum(
                    1 for b in brokers
                    if b["broker"] in SMART_MONEY_BROKERS and (b["buy_value"] + b["sell_value"]) > 0
                ),
            },
        }
