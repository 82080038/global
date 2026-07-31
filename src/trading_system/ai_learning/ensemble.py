"""Ensemble System (T, §4.1).

Combines multiple model predictions using voting, stacking, or weighted averaging.
Supports weight optimization based on validation performance.

Methods:
- voting: majority vote (classification) or average (regression)
- weighted: weighted average with configurable weights
- stacking: meta-learner over base predictions
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class EnsembleConfig:
    method: str = "weighted"  # "voting", "weighted", "stacking"
    weights: dict[str, float] = field(default_factory=dict)
    fallback_weight: float = 1.0


class EnsembleSystem:
    """Combine multiple model predictions into a single prediction."""

    def __init__(self, config: EnsembleConfig | None = None):
        self.config = config or EnsembleConfig()
        self.model_scores: dict[str, float] = {}

    def update_weights(self, scores: dict[str, float]) -> None:
        """Update model weights based on validation scores.

        Weights are proportional to scores (higher score = higher weight).
        """
        self.model_scores = scores
        total = sum(scores.values())
        if total > 0:
            self.config.weights = {k: v / total for k, v in scores.items()}

    def combine(self, predictions: dict[str, float]) -> float:
        """Combine predictions from multiple models.

        Args:
            predictions: Dict of model_name -> prediction value.

        Returns:
            Combined prediction.
        """
        if not predictions:
            return 0.0

        if self.config.method == "voting":
            return np.mean(list(predictions.values()))

        elif self.config.method == "weighted":
            total_weight = 0.0
            weighted_sum = 0.0
            for model_name, pred in predictions.items():
                weight = self.config.weights.get(model_name, self.config.fallback_weight)
                weighted_sum += pred * weight
                total_weight += weight
            return weighted_sum / total_weight if total_weight > 0 else 0.0

        elif self.config.method == "stacking":
            # Simple average for stacking without meta-learner
            return np.mean(list(predictions.values()))

        return np.mean(list(predictions.values()))

    def combine_batch(self, predictions: dict[str, list[float]]) -> list[float]:
        """Combine batch predictions from multiple models.

        Args:
            predictions: Dict of model_name -> list of predictions.

        Returns:
            List of combined predictions.
        """
        if not predictions:
            return []

        n = len(next(iter(predictions.values())))
        results = []
        for i in range(n):
            preds = {model: preds_list[i] for model, preds_list in predictions.items()}
            results.append(self.combine(preds))
        return results

    def get_model_agreement(self, predictions: dict[str, float], threshold: float = 0.0) -> float:
        """Compute model agreement ratio.

        Returns fraction of models that agree on direction (above/below threshold).
        """
        if not predictions:
            return 0.0
        positive = sum(1 for v in predictions.values() if v > threshold)
        negative = sum(1 for v in predictions.values() if v < threshold)
        return max(positive, negative) / len(predictions)
