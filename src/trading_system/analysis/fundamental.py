"""Fundamental Analysis Engine (Fase 2).

Menggunakan yfinance info/financials. Data .JK terbatas; jika gagal,
engine mengembalikan status warning dan skor null.
"""

from __future__ import annotations

import warnings

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

    def compute_score(self, ratios: dict) -> tuple[float, dict, float]:
        """Compute fundamental score using only available data.

        Missing data does NOT get a neutral 12.5 score. Instead, the score
        is normalized over available components only. A data_coverage ratio
        (0-1) is returned so callers can penalize or flag low-coverage scores.

        Returns: (score 0-100, breakdown, data_coverage 0-1)
        """
        breakdown = {}
        max_per_component = 25.0
        components = {}

        # Valuation (0-25): lower PER/PBV good
        per = ratios.get("PER")
        pbv = ratios.get("PBV")
        if per is not None:
            components["PER"] = min(max_per_component, max(0, 25 - (per / 5)))
        if pbv is not None:
            components["PBV"] = min(max_per_component, max(0, 25 - (pbv / 0.4)))

        # Profitability (0-25)
        roe = ratios.get("ROE")
        if roe is not None:
            components["ROE"] = min(max_per_component, roe)

        # Leverage (0-25): lower DER is better
        der = ratios.get("DER")
        if der is not None:
            components["DER"] = max(0, 25 - der * 25)

        # Growth (0-25)
        eps_g = ratios.get("eps_growth")
        rev_g = ratios.get("revenue_growth")
        if eps_g is not None or rev_g is not None:
            avg = ((eps_g or 0) + (rev_g or 0)) / 2
            components["growth"] = min(max_per_component, max(0, 12.5 + avg))

        # Calculate coverage
        total_possible = 5 * max_per_component  # PER, PBV, ROE, DER, growth
        data_coverage = len(components) / 5.0 if total_possible > 0 else 0.0

        # Score: normalize available component scores to 0-100 scale
        if components:
            raw_score = sum(components.values())
            # Scale: (raw / max_possible_for_available) * 100
            max_available = len(components) * max_per_component
            score = (raw_score / max_available) * 100 if max_available > 0 else 0.0
            # Penalize low coverage: reduce score proportionally when < 60% data available
            if data_coverage < 0.6:
                score *= data_coverage / 0.6
        else:
            score = 0.0

        breakdown = {k: round(v, 2) for k, v in components.items()}
        breakdown["_data_coverage"] = round(data_coverage, 2)
        breakdown["_missing"] = [c for c in ["PER", "PBV", "ROE", "DER", "growth"] if c not in components]

        return float(score), breakdown, data_coverage

    def analyze(self) -> dict:
        if not self.ticker:
            return {"status": "error", "message": "No ticker"}
        self.fetch(self.ticker)

        if not self.info:
            return {
                "status": "failed",
                "message": f"No fundamental data for {self.ticker} from yfinance",
                "engine": self.name,
                "score": None,
                "weight_multiplier": 0.0,
            }

        ratios = {}
        ratios.update(self.get_valuation())
        ratios.update(self.get_profitability())
        ratios.update(self.get_leverage())
        ratios.update(self.get_growth())

        score, breakdown, coverage = self.compute_score(ratios)

        status = "ok"
        weight_multiplier = 1.0
        if coverage < 0.4:
            status = "failed"
            weight_multiplier = 0.0
        elif coverage < 0.6:
            status = "degraded"
            weight_multiplier = 0.5

        return {
            "status": status,
            "engine": self.name,
            "score": round(score, 2) if weight_multiplier > 0 else None,
            "data_coverage": round(coverage, 2),
            "weight_multiplier": weight_multiplier,
            "ratios": {k: round(v, 4) if isinstance(v, float) else v for k, v in ratios.items()},
            "breakdown": breakdown,
        }
