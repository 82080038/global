"""Correlation-Aware Position Sizing (I, §4.1).

Adjusts position sizes based on correlation matrix to improve diversification.
Uses risk parity and correlation penalty to reduce concentrated bets.
"""

from __future__ import annotations

import numpy as np


class CorrelationPositionSizing:
    """Position sizing with correlation awareness."""

    @staticmethod
    def correlation_penalty(corr_matrix: np.ndarray, weights: np.ndarray) -> float:
        """Compute correlation penalty for a set of weights.

        Higher correlation = higher penalty = less effective diversification.

        Returns:
            Penalty factor (0 to 1). 1 = no penalty, 0 = max penalty.
        """
        if len(weights) < 2:
            return 1.0
        # Weighted average correlation
        n = len(weights)
        total_weight = 0.0
        weighted_corr = 0.0
        for i in range(n):
            for j in range(i + 1, n):
                w = weights[i] * weights[j]
                weighted_corr += abs(corr_matrix[i, j]) * w
                total_weight += w
        if total_weight < 1e-12:
            return 1.0
        avg_corr = weighted_corr / total_weight
        return float(1.0 - avg_corr)

    @staticmethod
    def risk_parity_weights(
        volatilities: np.ndarray,
        corr_matrix: np.ndarray,
    ) -> np.ndarray:
        """Compute risk parity weights (equal risk contribution).

        Args:
            volatilities: Array of per-asset volatilities.
            corr_matrix: Correlation matrix.

        Returns:
            Array of weights summing to 1.
        """
        n = len(volatilities)
        if n == 0:
            return np.array([])
        if n == 1:
            return np.array([1.0])

        # Inverse volatility weighting as starting point
        inv_vol = 1.0 / volatilities
        weights = inv_vol / np.sum(inv_vol)

        # Simple risk parity: iterate to equalize risk contributions
        for _ in range(100):
            portfolio_var = weights @ (corr_matrix * np.outer(volatilities, volatilities)) @ weights
            if portfolio_var < 1e-12:
                break
            marginal = (corr_matrix * np.outer(volatilities, volatilities)) @ weights
            risk_contrib = weights * marginal / portfolio_var
            target = 1.0 / n
            adjustment = target / (risk_contrib + 1e-12)
            weights = weights * adjustment
            weights = weights / np.sum(weights)

        return weights

    @staticmethod
    def diversification_ratio(
        weights: np.ndarray,
        volatilities: np.ndarray,
        corr_matrix: np.ndarray,
    ) -> float:
        """Compute diversification ratio.

        DR = weighted avg vol / portfolio vol
        Higher = more diversified.
        """
        if len(weights) < 2:
            return 1.0
        weighted_vol = np.sum(weights * volatilities)
        cov_matrix = corr_matrix * np.outer(volatilities, volatilities)
        portfolio_vol = np.sqrt(weights @ cov_matrix @ weights)
        if portfolio_vol < 1e-12:
            return 1.0
        return float(weighted_vol / portfolio_vol)

    @staticmethod
    def adjust_weights_for_correlation(
        raw_weights: np.ndarray,
        corr_matrix: np.ndarray,
        max_correlation: float = 0.7,
    ) -> np.ndarray:
        """Reduce weights for highly correlated assets.

        Args:
            raw_weights: Initial weight allocation.
            corr_matrix: Correlation matrix.
            max_correlation: Threshold above which to penalize.

        Returns:
            Adjusted weights (normalized to sum to 1).
        """
        n = len(raw_weights)
        if n < 2:
            return raw_weights

        adjusted = raw_weights.copy()
        for i in range(n):
            for j in range(i + 1, n):
                if abs(corr_matrix[i, j]) > max_correlation:
                    # Reduce both weights proportionally
                    penalty = 1.0 - (abs(corr_matrix[i, j]) - max_correlation) / (1.0 - max_correlation)
                    penalty = max(0.5, penalty)
                    adjusted[i] *= penalty
                    adjusted[j] *= penalty

        total = np.sum(adjusted)
        if total > 0:
            adjusted = adjusted / total
        return adjusted
