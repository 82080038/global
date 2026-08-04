"""Macro data adapters — FRED, BPS, Bank Indonesia.

Mengikuti pola DataSourceAdapter (§4.1) untuk sumber data makroekonomi.
Data disimpan ke tabel `macro_data` (series_name, date, value, unit, source, frequency).

Adapter:
    - FREDAdapter: Federal Reserve Economic Data (US rates, commodities, global macro)
    - BPSAdapter: Badan Pusat Statistik (GDP, inflation, trade, population)
    - BIAdapter: Bank Indonesia (BI rate, exchange rate, money supply)

Semua adapter menggunakan AdaptiveRateLimiter untuk rate limiting dan
menyimpan data via DataStorage.save_macro_data().
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from trading_system.data.adaptive_rate_limiter import AdaptiveRateLimiter
from trading_system.data.storage import DataStorage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# FRED Adapter — Federal Reserve Economic Data
# ---------------------------------------------------------------------------

# Series IDs yang relevan untuk analisis pasar modal Indonesia.
# Dokumentasi: https://fred.stlouisfed.org/categories
FRED_SERIES: dict[str, dict[str, str]] = {
    # US Interest Rates
    "DGS10": {"label": "US Treasury 10Y", "unit": "percent", "frequency": "daily"},
    "DGS2": {"label": "US Treasury 2Y", "unit": "percent", "frequency": "daily"},
    "DGS30": {"label": "US Treasury 30Y", "unit": "percent", "frequency": "daily"},
    "FEDFUNDS": {"label": "Fed Funds Rate", "unit": "percent", "frequency": "monthly"},
    "T10Y2Y": {"label": "US Yield Curve 10Y-2Y", "unit": "percent", "frequency": "daily"},
    # Commodities
    "DCOILWTICO": {"label": "WTI Crude Oil", "unit": "usd_per_barrel", "frequency": "daily"},
    "GOLDAMGBD228NLBM": {"label": "Gold London PM", "unit": "usd_per_oz", "frequency": "daily"},
    # US Macro
    "GDP": {"label": "US GDP", "unit": "billion_usd", "frequency": "quarterly"},
    "CPIAUCSL": {"label": "US CPI", "unit": "index", "frequency": "monthly"},
    "UNRATE": {"label": "US Unemployment", "unit": "percent", "frequency": "monthly"},
    # VIX / Volatility
    "VIXCLS": {"label": "VIX", "unit": "index", "frequency": "daily"},
    # Trade-weighted USD
    "DTWEXBGS": {"label": "Trade-Weighted USD Index", "unit": "index", "frequency": "daily"},
}

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"


class FREDAdapter:
    """FRED API adapter — fetch macro economic data from Federal Reserve.

    Requires API key from https://fred.stlouisfed.org/docs/api/api_key.html
    Set via env var FRED_API_KEY.

    Rate limit: 120 requests/minute (FRED documented limit).
    """

    name = "fred"

    def __init__(
        self,
        api_key: str | None = None,
        storage: DataStorage | None = None,
        rate_limiter: AdaptiveRateLimiter | None = None,
    ):
        import os

        self.api_key = api_key or os.getenv("FRED_API_KEY", "")
        self.storage = storage or DataStorage()
        self.rate_limiter = rate_limiter or AdaptiveRateLimiter.for_fred()

    def fetch_series(
        self,
        series_id: str,
        observation_start: str | None = None,
        observation_end: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a single FRED series and store to macro_data.

        Args:
            series_id: FRED series ID (e.g. 'DGS10', 'VIXCLS').
            observation_start: Start date YYYY-MM-DD (default: 5 years ago).
            observation_end: End date YYYY-MM-DD (default: today).

        Returns:
            dict with keys: status, records, message.
        """
        if not self.api_key:
            msg = "FRED_API_KEY not set — get free key at https://fred.stlouisfed.org/docs/api/api_key.html"
            logger.warning(msg)
            return {"status": "error", "records": pd.DataFrame(), "message": msg}

        meta = FRED_SERIES.get(series_id)
        if meta is None:
            # Allow custom series IDs not in our preset
            meta = {"label": series_id, "unit": "unknown", "frequency": "unknown"}

        if observation_start is None:
            observation_start = (datetime.now(UTC).replace(year=datetime.now(UTC).year - 5)).strftime("%Y-%m-%d")
        if observation_end is None:
            observation_end = datetime.now(UTC).strftime("%Y-%m-%d")

        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "observation_start": observation_start,
            "observation_end": observation_end,
        }

        def _do_fetch() -> pd.DataFrame:
            import requests

            resp = requests.get(FRED_BASE_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            obs = data.get("observations", [])
            if not obs:
                return pd.DataFrame()
            df = pd.DataFrame(obs)
            # FRED returns '.' for missing values
            df["value"] = pd.to_numeric(df["value"].replace(".", "NaN"), errors="coerce")
            df["date"] = df["date"].astype(str)
            return df[["date", "value"]]

        result = self.rate_limiter.execute(series_id, _do_fetch)

        if result.error:
            self.storage.update_source_health(self.name, "down", success=False)
            self.storage.audit(
                "data.macro.fred.error",
                {"series_id": series_id, "error": result.error, "attempts": result.attempts},
            )
            return {"status": "error", "records": pd.DataFrame(), "message": result.error}

        df = result.data
        if df is None or df.empty:
            self.storage.update_source_health(self.name, "degraded", success=True)
            return {"status": "empty", "records": pd.DataFrame(), "message": f"No data for {series_id}"}

        # Save to macro_data
        saved = 0
        for _, row in df.iterrows():
            if pd.isna(row["value"]):
                continue
            self.storage.save_macro_data({
                "series_name": meta["label"],
                "date": row["date"],
                "value": float(row["value"]),
                "unit": meta["unit"],
                "source": self.name,
                "frequency": meta["frequency"],
            })
            saved += 1

        self.storage.update_source_health(self.name, "ok", success=True)
        self.storage.audit(
            "data.macro.fred",
            {"series_id": series_id, "label": meta["label"], "rows": saved},
        )
        logger.info(f"FRED {series_id} ({meta['label']}): {saved} rows saved")
        return {"status": "ok", "records": df, "message": f"Fetched {saved} rows for {series_id}"}

    def fetch_all(
        self,
        observation_start: str | None = None,
        observation_end: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Fetch all configured FRED series.

        Returns dict mapping series_id → result dict.
        """
        results: dict[str, dict[str, Any]] = {}
        for sid in FRED_SERIES:
            results[sid] = self.fetch_series(sid, observation_start, observation_end)
        return results


# ---------------------------------------------------------------------------
# BPS Adapter — Badan Pusat Statistik
# ---------------------------------------------------------------------------

# BPS API: https://webapi.bps.go.id/v1/
# Requires API key from https://webapi.bps.go.id/v1/ (register via BPS website)
#
# Key indicators for IDX:
# - GDP growth (quarterly)
# - Inflation / CPI (monthly)
# - Trade balance (monthly)
# - Manufacturing PMI (monthly)
# - Retail sales (monthly)
# - Population (annual)

BPS_SERIES: dict[str, dict[str, str]] = {
    "gdp_growth": {"label": "Indonesia GDP Growth", "unit": "percent_yoy", "frequency": "quarterly"},
    "inflation_yoy": {"label": "Indonesia Inflation YoY", "unit": "percent_yoy", "frequency": "monthly"},
    "inflation_mom": {"label": "Indonesia Inflation MoM", "unit": "percent_mom", "frequency": "monthly"},
    "trade_balance": {"label": "Indonesia Trade Balance", "unit": "million_usd", "frequency": "monthly"},
    "exports": {"label": "Indonesia Exports", "unit": "million_usd", "frequency": "monthly"},
    "imports": {"label": "Indonesia Imports", "unit": "million_usd", "frequency": "monthly"},
    "manufacturing_pmi": {"label": "Indonesia Manufacturing PMI", "unit": "index", "frequency": "monthly"},
    "retail_sales": {"label": "Indonesia Retail Sales", "unit": "index", "frequency": "monthly"},
    "unemployment": {"label": "Indonesia Unemployment", "unit": "percent", "frequency": "quarterly"},
}

BPS_BASE_URL = "https://webapi.bps.go.id/v1/api/list"


class BPSAdapter:
    """BPS (Badan Pusat Statistik) API adapter.

    Fetches Indonesian macroeconomic indicators from BPS REST API.
    Requires API key from https://webapi.bps.go.id/v1/
    Set via env var BPS_API_KEY.

    Rate limit: BPS does not document a strict limit, but be respectful
    (default 1 req/sec).
    """

    name = "bps"

    def __init__(
        self,
        api_key: str | None = None,
        storage: DataStorage | None = None,
        rate_limiter: AdaptiveRateLimiter | None = None,
    ):
        import os

        self.api_key = api_key or os.getenv("BPS_API_KEY", "")
        self.storage = storage or DataStorage()
        self.rate_limiter = rate_limiter or AdaptiveRateLimiter.for_bps()

    def _build_params(self, model: str, **kwargs) -> dict[str, str]:
        """Build BPS API query params."""
        params = {
            "model": model,
            "domain": "0000",  # National level
            "key": self.api_key,
            "lang": "ind",
            "var": kwargs.get("var", ""),
            "turvar": kwargs.get("turvar", ""),
            "th": kwargs.get("th", ""),
            "turth": kwargs.get("turth", ""),
            "page": kwargs.get("page", "1"),
            "perpage": kwargs.get("perpage", "100"),
        }
        return {k: v for k, v in params.items() if v}

    def fetch_series(
        self,
        series_key: str,
        var_id: str,
        year_start: int | None = None,
        year_end: int | None = None,
    ) -> dict[str, Any]:
        """Fetch a BPS data series by variable ID.

        Args:
            series_key: Key in BPS_SERIES (e.g. 'gdp_growth').
            var_id: BPS variable ID (from BPS API catalog).
            year_start: Start year (default: 5 years ago).
            year_end: End year (default: current year).

        Returns:
            dict with keys: status, records, message.
        """
        if not self.api_key:
            msg = "BPS_API_KEY not set — register at https://webapi.bps.go.id/v1/"
            logger.warning(msg)
            return {"status": "error", "records": pd.DataFrame(), "message": msg}

        meta = BPS_SERIES.get(series_key, {"label": series_key, "unit": "unknown", "frequency": "unknown"})

        if year_start is None:
            year_start = datetime.now(UTC).year - 5
        if year_end is None:
            year_end = datetime.now(UTC).year

        params = self._build_params(
            model="data",
            var=var_id,
            th=f"{year_start}-{year_end}",
            perpage="500",
        )

        def _do_fetch() -> pd.DataFrame:
            import requests

            resp = requests.get(BPS_BASE_URL, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            records = data.get("datacontent", data.get("data", []))
            if not records:
                return pd.DataFrame()

            # BPS returns list of dicts with varying keys depending on indicator
            rows = []
            for item in records:
                date_str = item.get("tgl", item.get("date", item.get("periode", "")))
                val = item.get("value", item.get("nilai"))
                if date_str and val is not None:
                    try:
                        val = float(str(val).replace(",", "").replace(".", ""))
                    except (ValueError, TypeError):
                        continue
                    rows.append({"date": str(date_str), "value": val})

            if not rows:
                return pd.DataFrame()
            return pd.DataFrame(rows)

        result = self.rate_limiter.execute(series_key, _do_fetch)

        if result.error:
            self.storage.update_source_health(self.name, "down", success=False)
            self.storage.audit(
                "data.macro.bps.error",
                {"series_key": series_key, "var_id": var_id, "error": result.error},
            )
            return {"status": "error", "records": pd.DataFrame(), "message": result.error}

        df = result.data
        if df is None or df.empty:
            self.storage.update_source_health(self.name, "degraded", success=True)
            return {"status": "empty", "records": pd.DataFrame(), "message": f"No data for {series_key}"}

        saved = 0
        for _, row in df.iterrows():
            self.storage.save_macro_data({
                "series_name": meta["label"],
                "date": row["date"],
                "value": float(row["value"]),
                "unit": meta["unit"],
                "source": self.name,
                "frequency": meta["frequency"],
            })
            saved += 1

        self.storage.update_source_health(self.name, "ok", success=True)
        self.storage.audit(
            "data.macro.bps",
            {"series_key": series_key, "var_id": var_id, "rows": saved},
        )
        logger.info(f"BPS {series_key} ({meta['label']}): {saved} rows saved")
        return {"status": "ok", "records": df, "message": f"Fetched {saved} rows for {series_key}"}

    def fetch_all(self, var_ids: dict[str, str] | None = None) -> dict[str, dict[str, Any]]:
        """Fetch all configured BPS series.

        Args:
            var_ids: Mapping of series_key → BPS variable ID.
                     If None, only series with known var_ids will be fetched.

        Returns dict mapping series_key → result dict.
        """
        var_ids = var_ids or {}
        results: dict[str, dict[str, Any]] = {}
        for sk in BPS_SERIES:
            vid = var_ids.get(sk)
            if vid:
                results[sk] = self.fetch_series(sk, vid)
            else:
                results[sk] = {
                    "status": "skipped",
                    "records": pd.DataFrame(),
                    "message": f"No var_id provided for {sk} — see BPS API catalog",
                }
        return results


# ---------------------------------------------------------------------------
# Bank Indonesia Adapter
# ---------------------------------------------------------------------------

# BI provides data via:
# 1. Web scraping https://www.bi.go.id/id/statistik/ (no official REST API)
# 2. JSON endpoints used by their website (undocumented, but stable)
#
# Key indicators:
# - BI 7-Day Reverse Repo Rate (policy rate)
# - BI Rate (old benchmark, pre-2016)
# - USD/IDR exchange rate (Jisdor)
# - Interbank rate
# - Money supply (M0, M1, M2)
# - Foreign reserves
# - Government bond yields

BI_SERIES: dict[str, dict[str, str]] = {
    "bi_rate": {"label": "BI 7-Day Reverse Repo Rate", "unit": "percent", "frequency": "monthly"},
    "bi_rate_old": {"label": "BI Rate (old benchmark)", "unit": "percent", "frequency": "monthly"},
    "usd_idr_jisdor": {"label": "USD/IDR Jisdor", "unit": "idr_per_usd", "frequency": "daily"},
    "interbank_rate": {"label": "Interbank Overnight Rate", "unit": "percent", "frequency": "daily"},
    "m0": {"label": "Money Supply M0", "unit": "billion_idr", "frequency": "monthly"},
    "m1": {"label": "Money Supply M1", "unit": "billion_idr", "frequency": "monthly"},
    "m2": {"label": "Money Supply M2", "unit": "billion_idr", "frequency": "monthly"},
    "foreign_reserves": {"label": "Foreign Exchange Reserves", "unit": "billion_usd", "frequency": "monthly"},
    "gov_bond_10y": {"label": "Indonesia Gov Bond 10Y Yield", "unit": "percent", "frequency": "daily"},
}

# BI undocumented JSON endpoints (used by bi.go.id frontend)
BI_ENDPOINTS: dict[str, str] = {
    "bi_rate": "https://www.bi.go.id/_next/data/statistik/moneter/bi-rate/data.json",
    "usd_idr_jisdor": "https://www.bi.go.id/_next/data/statistik/kurs/reference-rate/data.json",
    "gov_bond_10y": "https://www.bi.go.id/_next/data/statistik/pasar-uang/sbn-yield/data.json",
}


class BIAdapter:
    """Bank Indonesia data adapter.

    Fetches Indonesian monetary indicators from BI website JSON endpoints.
    No official API key required (endpoints are public but undocumented).

    Fallback: scrape HTML pages if JSON endpoints change.
    Rate limit: conservative 1 req/2sec (BI is a government site).
    """

    name = "bank_indonesia"

    def __init__(
        self,
        storage: DataStorage | None = None,
        rate_limiter: AdaptiveRateLimiter | None = None,
    ):
        self.storage = storage or DataStorage()
        self.rate_limiter = rate_limiter or AdaptiveRateLimiter.for_bi()

    def fetch_series(
        self,
        series_key: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a BI data series.

        Args:
            series_key: Key in BI_SERIES (e.g. 'bi_rate', 'usd_idr_jisdor').
            start_date: Start date YYYY-MM-DD (default: 5 years ago).
            end_date: End date YYYY-MM-DD (default: today).

        Returns:
            dict with keys: status, records, message.
        """
        meta = BI_SERIES.get(series_key)
        if meta is None:
            return {"status": "error", "records": pd.DataFrame(), "message": f"Unknown series: {series_key}"}

        if start_date is None:
            start_date = (datetime.now(UTC).replace(year=datetime.now(UTC).year - 5)).strftime("%Y-%m-%d")
        if end_date is None:
            end_date = datetime.now(UTC).strftime("%Y-%m-%d")

        endpoint = BI_ENDPOINTS.get(series_key)
        if endpoint is None:
            msg = (
                f"No BI endpoint configured for '{series_key}'. "
                f"Available: {list(BI_ENDPOINTS.keys())}"
            )
            logger.warning(msg)
            return {"status": "error", "records": pd.DataFrame(), "message": msg}

        def _do_fetch() -> pd.DataFrame:
            import requests

            resp = requests.get(
                endpoint,
                timeout=20,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "trading-system/0.1 (data research)",
                    "Referer": "https://www.bi.go.id/",
                },
            )
            resp.raise_for_status()
            data = resp.json()

            # BI JSON structure varies per endpoint — try common patterns
            records = (
                data.get("data", data.get("result", data.get("pageProps", {}).get("data", [])))
            )
            if isinstance(records, dict):
                records = records.get("datacontent", records.get("items", []))
            if not isinstance(records, list):
                records = []

            if not records:
                return pd.DataFrame()

            rows = []
            for item in records:
                # Try multiple field name conventions
                date_str = (
                    item.get("tgl")
                    or item.get("date")
                    or item.get("periode")
                    or item.get("tanggal")
                    or ""
                )
                val = item.get("value") or item.get("nilai") or item.get("rate") or item.get("harga")
                if date_str and val is not None:
                    try:
                        val = float(str(val).replace(",", "").replace(" ", ""))
                    except (ValueError, TypeError):
                        continue
                    rows.append({"date": str(date_str), "value": val})

            if not rows:
                return pd.DataFrame()
            df = pd.DataFrame(rows)
            # Filter by date range
            df["date_parsed"] = pd.to_datetime(df["date"], format="mixed", errors="coerce")
            mask = (df["date_parsed"] >= pd.to_datetime(start_date)) & (
                df["date_parsed"] <= pd.to_datetime(end_date)
            )
            df = df[mask].drop(columns=["date_parsed"]).reset_index(drop=True)
            return df

        result = self.rate_limiter.execute(series_key, _do_fetch)

        if result.error:
            self.storage.update_source_health(self.name, "down", success=False)
            self.storage.audit(
                "data.macro.bi.error",
                {"series_key": series_key, "error": result.error},
            )
            return {"status": "error", "records": pd.DataFrame(), "message": result.error}

        df = result.data
        if df is None or df.empty:
            self.storage.update_source_health(self.name, "degraded", success=True)
            return {"status": "empty", "records": pd.DataFrame(), "message": f"No data for {series_key}"}

        saved = 0
        for _, row in df.iterrows():
            self.storage.save_macro_data({
                "series_name": meta["label"],
                "date": row["date"],
                "value": float(row["value"]),
                "unit": meta["unit"],
                "source": self.name,
                "frequency": meta["frequency"],
            })
            saved += 1

        self.storage.update_source_health(self.name, "ok", success=True)
        self.storage.audit(
            "data.macro.bi",
            {"series_key": series_key, "label": meta["label"], "rows": saved},
        )
        logger.info(f"BI {series_key} ({meta['label']}): {saved} rows saved")
        return {"status": "ok", "records": df, "message": f"Fetched {saved} rows for {series_key}"}

    def fetch_all(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Fetch all BI series that have configured endpoints.

        Returns dict mapping series_key → result dict.
        """
        results: dict[str, dict[str, Any]] = {}
        for sk in BI_ENDPOINTS:
            results[sk] = self.fetch_series(sk, start_date, end_date)
        return results
