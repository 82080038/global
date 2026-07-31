"""Performance Attribution Engine (H, §4.1).

Decomposes portfolio returns into factor and sector contributions
to identify sources of alpha and beta.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class PerformanceAttribution:
    """Attribute portfolio returns to factors and sectors."""

    @staticmethod
    def attribute_by_sector(
        returns: pd.DataFrame,
        weights: dict[str, float],
        sector_map: dict[str, str],
    ) -> dict[str, float]:
        """Attribute returns by sector.

        Args:
            returns: DataFrame of asset returns (columns = symbols).
            weights: Dict of symbol -> portfolio weight.
            sector_map: Dict of symbol -> sector name.

        Returns:
            Dict of sector -> contribution to portfolio return.
        """
        sector_contributions: dict[str, float] = {}
        for symbol, weight in weights.items():
            if symbol not in returns.columns:
                continue
            sector = sector_map.get(symbol, "unknown")
            asset_return = float(returns[symbol].mean())
            contribution = asset_return * weight
            sector_contributions[sector] = sector_contributions.get(sector, 0.0) + contribution

        return {k: round(v, 6) for k, v in sector_contributions.items()}

    @staticmethod
    def attribute_by_factor(
        returns: pd.DataFrame,
        factor_exposures: dict[str, dict[str, float]],
        factor_returns: dict[str, float],
    ) -> dict[str, float]:
        """Attribute returns by factor.

        Args:
            returns: DataFrame of asset returns.
            factor_exposures: Dict of symbol -> {factor_name -> exposure}.
            factor_returns: Dict of factor_name -> factor return.

        Returns:
            Dict of factor -> contribution to portfolio return.
        """
        factor_contributions: dict[str, float] = {}
        for symbol, exposures in factor_exposures.items():
            if symbol not in returns.columns:
                continue
            for factor_name, exposure in exposures.items():
                f_return = factor_returns.get(factor_name, 0.0)
                contribution = exposure * f_return
                factor_contributions[factor_name] = factor_contributions.get(factor_name, 0.0) + contribution

        return {k: round(v, 6) for k, v in factor_contributions.items()}

    @staticmethod
    def compute_attribution(
        portfolio_returns: pd.Series,
        benchmark_returns: pd.Series,
    ) -> dict[str, float]:
        """Compute basic attribution: alpha and beta vs benchmark.

        Returns:
            Dict with alpha, beta, tracking_error, information_ratio.
        """
        if len(portfolio_returns) < 2 or len(benchmark_returns) < 2:
            return {"alpha": 0.0, "beta": 0.0, "tracking_error": 0.0, "information_ratio": 0.0}

        min_len = min(len(portfolio_returns), len(benchmark_returns))
        p = portfolio_returns.values[-min_len:]
        b = benchmark_returns.values[-min_len:]

        var_b = np.var(b, ddof=1)
        if var_b < 1e-12:
            beta = 0.0
        else:
            beta = float(np.cov(p, b, ddof=1)[0, 1] / var_b)

        alpha = float(np.mean(p) - beta * np.mean(b))
        tracking_error = float(np.std(p - b, ddof=1))
        information_ratio = alpha / tracking_error if tracking_error > 1e-12 else 0.0

        return {
            "alpha": round(alpha, 6),
            "beta": round(beta, 6),
            "tracking_error": round(tracking_error, 6),
            "information_ratio": round(information_ratio, 6),
        }
