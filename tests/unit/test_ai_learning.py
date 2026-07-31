"""Unit tests for AILearningEngine."""

import json
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock

from trading_system.ai_learning.engine import AILearningEngine, REGIME_WEIGHTS


class TestAILearningEngine:

    def test_get_factor_weights_no_ticker_returns_regime_weights(self, mock_storage):
        """Without ticker, should return regime-based weights."""
        engine = AILearningEngine(storage=mock_storage)
        weights = engine.get_factor_weights(regime="easing")

        assert weights == REGIME_WEIGHTS["easing"]

    def test_get_factor_weights_unknown_regime_returns_default(self, mock_storage):
        """Unknown regime should fall back to DEFAULT_WEIGHTS."""
        from trading_system.decision.engine import DEFAULT_WEIGHTS

        engine = AILearningEngine(storage=mock_storage)
        weights = engine.get_factor_weights(regime="unknown_regime")

        assert weights == DEFAULT_WEIGHTS

    def test_get_factor_weights_no_history_returns_base(self, mock_storage):
        """No score history should return base regime weights."""
        mock_storage.load_scores.return_value = pd.DataFrame()
        engine = AILearningEngine(storage=mock_storage)
        weights = engine.get_factor_weights(ticker="TEST.JK", regime="neutral")

        # Should return default weights (neutral regime)
        from trading_system.decision.engine import DEFAULT_WEIGHTS
        assert weights == DEFAULT_WEIGHTS

    def test_get_factor_weights_with_history_adjusts(self, mock_storage):
        """Historical scores should adjust weights."""
        scores_df = pd.DataFrame({
            "engine": ["technical", "fundamental", "macro", "global", "relationship", "sentiment"],
            "score": [75, 65, 55, 60, 50, 58],
            "as_of": ["2024-01-01"] * 6,
            "breakdown": [json.dumps({})] * 6,
        })
        mock_storage.load_scores.return_value = scores_df

        engine = AILearningEngine(storage=mock_storage)
        weights = engine.get_factor_weights(ticker="TEST.JK", regime="neutral")

        # Weights should be normalized (sum to 1)
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.01

    def test_get_factor_weights_low_fundamental_coverage_penalized(self, mock_storage):
        """Low data coverage in fundamental should reduce its weight."""
        scores_df = pd.DataFrame({
            "engine": ["technical", "fundamental", "macro", "global", "relationship", "sentiment"],
            "score": [75, 50, 55, 60, 50, 58],
            "as_of": ["2024-01-01"] * 6,
            "breakdown": [
                "{}",
                json.dumps({"_data_coverage": 0.2}),  # Very low coverage
                "{}", "{}", "{}", "{}",
            ],
        })
        mock_storage.load_scores.return_value = scores_df

        engine = AILearningEngine(storage=mock_storage)
        weights = engine.get_factor_weights(ticker="TEST.JK", regime="neutral")

        # Fundamental weight should be reduced compared to default
        from trading_system.decision.engine import DEFAULT_WEIGHTS
        assert weights["fundamental"] < DEFAULT_WEIGHTS["fundamental"]

    def test_feature_importance(self):
        """Feature importance should compute relative weights."""
        engine = AILearningEngine(storage=MagicMock())
        scores = {"technical": 80, "fundamental": 60, "macro": 40}
        importance = engine.feature_importance(scores)

        assert len(importance) == 3
        total = sum(item["importance"] for item in importance)
        assert abs(total - 1.0) < 0.01

    def test_feature_importance_empty(self):
        """Empty scores should return empty list."""
        engine = AILearningEngine(storage=MagicMock())
        importance = engine.feature_importance({})
        assert importance == []

    def test_get_regime_no_ticker(self, mock_storage):
        """No ticker should return neutral regime."""
        engine = AILearningEngine(storage=mock_storage)
        assert engine.get_regime() == "neutral"

    def test_get_regime_no_macro_data(self, mock_storage):
        """No macro data should return neutral regime."""
        mock_storage.load_scores.return_value = pd.DataFrame()
        engine = AILearningEngine(storage=mock_storage)
        assert engine.get_regime("TEST.JK") == "neutral"

    def test_get_regime_from_macro_data(self, mock_storage):
        """Should extract regime from macro breakdown."""
        scores_df = pd.DataFrame({
            "engine": ["macro"],
            "score": [55],
            "as_of": ["2024-01-01"],
            "breakdown": [json.dumps({"regime": "tightening"})],
        })
        mock_storage.load_scores.return_value = scores_df
        engine = AILearningEngine(storage=mock_storage)
        assert engine.get_regime("TEST.JK") == "tightening"
