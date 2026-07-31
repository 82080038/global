"""Macro Economic Engine (Fase 2).

Menggunakan proxy Yahoo Finance: US 10Y, Gold, Oil, USD/IDR, DXY.
Output: macro_score dan macro_regime (easing, tightening, growth, slowdown).
"""

from __future__ import annotations

from datetime import UTC

from trading_system.config import DEFAULT_MACRO_TICKERS
from trading_system.data.acquisition import YahooFinanceAdapter, normalize_ohlcv
from trading_system.data.storage import DataStorage
from trading_system.data.validation import DataQualityValidator


class MacroEconomicEngine:
    name = "macro"

    def __init__(self, storage: DataStorage | None = None):
        self.storage = storage or DataStorage()
        self.adapter = YahooFinanceAdapter()
        self.validator = DataQualityValidator()

    def ensure_data(self, period: str = "2y", max_age_days: int = 1):
        """Fetch data if empty or stale (§4.2 SARAN_PENGEMBANGAN.md).

        Refresh jika umur data > ``max_age_days`` hari bursa.
        """
        from datetime import datetime, timedelta

        for label, ticker in DEFAULT_MACRO_TICKERS.items():
            df = self.storage.load_ohlcv(ticker)
            need_fetch = df.empty
            if not df.empty:
                last_ts = df.index[-1]
                if hasattr(last_ts, "tzinfo") and last_ts.tzinfo is None:
                    last_ts = last_ts.tz_localize("UTC")
                age = datetime.now(UTC) - last_ts
                if age > timedelta(days=max_age_days):
                    need_fetch = True
            if need_fetch:
                result = self.adapter.fetch(ticker, period=period)
                if result["status"] == "ok":
                    raw = normalize_ohlcv(result["records"])
                    clean, _ = self.validator.validate(raw)
                    self.storage.save_ohlcv(clean)

    def load_latest(self, ticker: str) -> tuple[float, float] | None:
        df = self.storage.load_ohlcv(ticker)
        if df.empty:
            return None
        last = df.iloc[-1]
        prev = df.iloc[-20] if len(df) >= 20 else df.iloc[0]
        return float(last["close"]), float(prev["close"])

    def classify_regime(self, rates: dict) -> str:
        # Sederhana: kalau suku bunga (US10Y) naik dan emas turun -> tightening
        # Kalau suku bunga turun dan emas naik -> easing
        # Kalau oil naik + USD/IDR turun -> growth
        # Kalau oil turun + USD/IDR naik -> slowdown
        try:
            us10y_now, us10y_prev = rates["US10Y"] if rates["US10Y"] else (None, None)
            gold_now, _ = rates["GOLD"] if rates["GOLD"] else (None, None)
            oil_now, _ = rates["OIL"] if rates["OIL"] else (None, None)
            usd_idr_now, _ = rates["USD_IDR"] if rates["USD_IDR"] else (None, None)

            if us10y_now is None:
                return "unknown"

            if us10y_now > us10y_prev:
                return "tightening"
            if us10y_now < us10y_prev:
                return "easing"
            if oil_now is not None and usd_idr_now is not None:
                return "growth" if oil_now > 0 else "slowdown"
            return "neutral"
        except Exception:
            return "unknown"

    # Mapping dari regime internal ke TIP-compatible taxonomy (§13.4 #6)
    REGIME_MAP = {
        "easing": "risk_on",
        "growth": "risk_on",
        "tightening": "risk_off",
        "slowdown": "risk_off",
        "neutral": "neutral",
        "unknown": "neutral",
    }

    def map_regime(self, regime: str) -> str:
        """Map internal regime to TIP-compatible regime (risk_on/risk_off/neutral).

        Used by Alpha Composer (Y) and No-Trade Engine (Z) from TIP.
        """
        return self.REGIME_MAP.get(regime, "neutral")

    def compute_score(self, rates: dict, regime: str) -> tuple[float, dict]:
        breakdown = {}
        # US10Y: naik buruk untuk saham, turun baik
        us10y = rates["US10Y"][0] if rates["US10Y"] else None
        if us10y is not None:
            breakdown["us10y"] = max(0, 25 - us10y * 2.5)
        else:
            breakdown["us10y"] = 12.5

        # Gold: naik menunjukkan risk-off
        gold = rates["GOLD"][0] if rates["GOLD"] else None
        gold_prev = rates["GOLD"][1] if rates["GOLD"] else None
        if gold is not None and gold_prev is not None:
            chg = (gold - gold_prev) / gold_prev
            breakdown["gold"] = 25 if chg < 0.05 else (12.5 if chg < 0.10 else 0)
        else:
            breakdown["gold"] = 12.5

        # Oil: naik = inflasi/growth, sedang baik
        oil = rates["OIL"][0] if rates["OIL"] else None
        if oil is not None:
            breakdown["oil"] = 25 if 60 <= oil <= 90 else 15
        else:
            breakdown["oil"] = 12.5

        # USD/IDR: turun baik untuk IDR, naik buruk
        usd_idr = rates["USD_IDR"][0] if rates["USD_IDR"] else None
        usd_idr_prev = rates["USD_IDR"][1] if rates["USD_IDR"] else None
        if usd_idr is not None and usd_idr_prev is not None:
            chg = (usd_idr - usd_idr_prev) / usd_idr_prev
            breakdown["usd_idr"] = 25 if chg < 0 else 12.5
        else:
            breakdown["usd_idr"] = 12.5

        score = sum(breakdown.values())
        return score, breakdown

    def analyze(self, period: str = "2y") -> dict:
        self.ensure_data(period)
        rates = {}
        for label, ticker in DEFAULT_MACRO_TICKERS.items():
            rates[label] = self.load_latest(ticker)

        regime = self.classify_regime(rates)
        score, breakdown = self.compute_score(rates, regime)
        breakdown["regime"] = regime

        # Data age tracking (§4.2)
        from datetime import datetime
        data_ages = {}
        for label, ticker in DEFAULT_MACRO_TICKERS.items():
            df = self.storage.load_ohlcv(ticker)
            if not df.empty:
                last_ts = df.index[-1]
                if hasattr(last_ts, "tzinfo") and last_ts.tzinfo is None:
                    last_ts = last_ts.tz_localize("UTC")
                age = (datetime.now(UTC) - last_ts).days
                data_ages[label] = age
            else:
                data_ages[label] = None
        breakdown["data_age_days"] = data_ages

        return {
            "status": "ok",
            "engine": self.name,
            "score": round(score, 2),
            "regime": regime,
            "rates": {k: v[0] if v else None for k, v in rates.items()},
            "breakdown": breakdown,
        }
