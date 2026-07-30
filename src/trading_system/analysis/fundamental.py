"""Fundamental Analysis Engine (Fase 2).

Menggunakan yfinance info/financials. Data .JK terbatas; jika gagal,
engine mengembalikan status warning dan skor null.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore", category=FutureWarning)


class FundamentalAnalysisEngine:
    name = "fundamental"

    def __init__(self, ticker: str | None = None):
        self.ticker = ticker
        self.info = {}
        self.financials = None
        self.balance = None
        self.cashflow = None

    def fetch(self, ticker: str | None = None):
        if ticker:
            self.ticker = ticker
        t = yf.Ticker(self.ticker)
        try:
            self.info = t.info or {}
        except Exception:
            self.info = {}
        try:
            self.financials = t.financials
        except Exception:
            self.financials = None
        try:
            self.balance = t.balance_sheet
        except Exception:
            self.balance = None
        try:
            self.cashflow = t.cashflow
        except Exception:
            self.cashflow = None

    def get_valuation(self) -> dict:
        pe = self.info.get("trailingPE") or self.info.get("forwardPE")
        pb = self.info.get("priceToBook")
        ps = self.info.get("priceToSalesTrailing12Months")
        div_yield = self.info.get("dividendYield") or 0
        return {
            "PER": float(pe) if pe else None,
            "PBV": float(pb) if pb else None,
            "PS": float(ps) if ps else None,
            "dividend_yield": float(div_yield) * 100 if div_yield else 0,
        }

    def get_profitability(self) -> dict:
        # ROE from info or balance/income
        roe = self.info.get("returnOnEquity")
        roa = self.info.get("returnOnAssets")
        margins = {
            "gross_margin": self.info.get("grossMargins"),
            "operating_margin": self.info.get("operatingMargins"),
            "net_margin": self.info.get("profitMargins"),
        }
        return {
            "ROE": float(roe) * 100 if roe else None,
            "ROA": float(roa) * 100 if roa else None,
            **{k: float(v) * 100 if v else None for k, v in margins.items()},
        }

    def get_leverage(self) -> dict:
        if self.balance is None or self.balance.empty:
            return {"DER": None, "Debt_to_Asset": None}
        # Coba cari total debt / total equity / total assets
        def find_row(keywords):
            for k in self.balance.index:
                if any(w.lower() in k.lower() for w in keywords):
                    return self.balance.loc[k]
            return None

        total_debt = find_row(["total debt", "total liabilities"])
        total_equity = find_row(["stockholders equity", "total equity"])
        total_assets = find_row(["total assets"])

        der = None
        if total_debt is not None and total_equity is not None:
            try:
                der = float(total_debt.iloc[0]) / float(total_equity.iloc[0])
            except Exception:
                pass
        dta = None
        if total_debt is not None and total_assets is not None:
            try:
                dta = float(total_debt.iloc[0]) / float(total_assets.iloc[0])
            except Exception:
                pass
        return {"DER": der, "Debt_to_Asset": dta}

    def get_growth(self) -> dict:
        growth = {"revenue_growth": None, "eps_growth": None}
        if self.info.get("earningsGrowth"):
            growth["eps_growth"] = float(self.info["earningsGrowth"]) * 100
        if self.info.get("revenueGrowth"):
            growth["revenue_growth"] = float(self.info["revenueGrowth"]) * 100
        return growth

    def compute_score(self, ratios: dict) -> tuple[float, dict]:
        breakdown = {}

        # Valuation (0-25): lower PER/PBV good
        per = ratios.get("PER")
        pbv = ratios.get("PBV")
        if per is not None:
            breakdown["PER"] = min(25, max(0, 25 - (per / 5)))  # 0 PER -> 25, PER 50+ -> 0
        else:
            breakdown["PER"] = 12.5
        if pbv is not None:
            breakdown["PBV"] = min(25, max(0, 25 - (pbv / 0.4)))
        else:
            breakdown["PBV"] = 12.5

        # Profitability (0-25)
        roe = ratios.get("ROE")
        if roe is not None:
            breakdown["ROE"] = min(25, roe)
        else:
            breakdown["ROE"] = 12.5

        # Leverage (0-25): lower DER is better
        der = ratios.get("DER")
        if der is not None:
            breakdown["DER"] = max(0, 25 - der * 25)
        else:
            breakdown["DER"] = 12.5

        # Growth (0-25)
        eps_g = ratios.get("eps_growth") or 0
        rev_g = ratios.get("revenue_growth") or 0
        if eps_g is not None or rev_g is not None:
            avg = ((eps_g or 0) + (rev_g or 0)) / 2
            breakdown["growth"] = min(25, max(0, 12.5 + avg))
        else:
            breakdown["growth"] = 12.5

        score = sum(breakdown.values())
        return float(score), breakdown

    def analyze(self) -> dict:
        if not self.ticker:
            return {"status": "error", "message": "No ticker"}
        self.fetch(self.ticker)

        if not self.info:
            return {
                "status": "warning",
                "message": f"No fundamental data for {self.ticker} from yfinance",
                "engine": self.name,
                "score": None,
            }

        ratios = {}
        ratios.update(self.get_valuation())
        ratios.update(self.get_profitability())
        ratios.update(self.get_leverage())
        ratios.update(self.get_growth())

        score, breakdown = self.compute_score(ratios)
        return {
            "status": "ok",
            "engine": self.name,
            "score": round(score, 2),
            "ratios": {k: round(v, 4) if isinstance(v, float) else v for k, v in ratios.items()},
            "breakdown": breakdown,
        }
