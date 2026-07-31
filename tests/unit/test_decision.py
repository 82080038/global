"""Unit tests for DecisionEngine."""

import json
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock

from trading_system.decision.engine import DecisionEngine, DEFAULT_WEIGHTS


class TestDecisionEngine:

    def test_compute_conviction_basic(self, mock_storage):
        """Conviction should be weighted average of scores."""
        engine = DecisionEngine(storage=mock_storage)
        scores = {"technical": 80, "fundamental": 60, "macro": 50, "global": 70, "relationship": 55, "sentiment": 65}
        conviction = engine.compute_conviction(scores)

        # Weighted average
        expected = sum(scores[k] * DEFAULT_WEIGHTS[k] for k in DEFAULT_WEIGHTS if k in scores)
        expected /= sum(DEFAULT_WEIGHTS[k] for k in DEFAULT_WEIGHTS if k in scores)
        assert abs(conviction - expected) < 0.01

    def test_compute_conviction_empty(self, mock_storage):
        """Empty scores should give 0 conviction."""
        engine = DecisionEngine(storage=mock_storage)
        conviction = engine.compute_conviction({})
        assert conviction == 0.0

    def test_decide_action_buy(self, mock_storage):
        """High conviction should return BUY."""
        engine = DecisionEngine(storage=mock_storage)
        assert engine.decide_action(75, []) == "BUY"

    def test_decide_action_watchlist(self, mock_storage):
        """Medium-high conviction should return WATCHLIST."""
        engine = DecisionEngine(storage=mock_storage)
        assert engine.decide_action(60, []) == "WATCHLIST"

    def test_decide_action_hold(self, mock_storage):
        """Medium conviction should return HOLD."""
        engine = DecisionEngine(storage=mock_storage)
        assert engine.decide_action(45, []) == "HOLD"

    def test_decide_action_avoid(self, mock_storage):
        """Low conviction should return AVOID."""
        engine = DecisionEngine(storage=mock_storage)
        assert engine.decide_action(30, []) == "AVOID"

    def test_decide_action_avoid_with_risk_flags(self, mock_storage):
        """High conviction but HIGH_VOLATILITY should return AVOID if < 60."""
        engine = DecisionEngine(storage=mock_storage)
        assert engine.decide_action(55, ["HIGH_VOLATILITY"]) == "AVOID"

    def test_decide_action_buy_with_risk_flags_high_conviction(self, mock_storage):
        """High conviction with risk flags but >= 60 should still BUY."""
        engine = DecisionEngine(storage=mock_storage)
        assert engine.decide_action(75, ["HIGH_VOLATILITY"]) == "BUY"

    def test_apply_regime_filter_tightening(self, mock_storage):
        """Tightening regime should reduce macro and technical scores."""
        engine = DecisionEngine(storage=mock_storage)
        scores = {"technical": 80, "macro": 60, "fundamental": 70}
        adjusted = engine.apply_regime_filter(scores, "tightening")

        assert adjusted["macro"] < scores["macro"]
        assert adjusted["technical"] < scores["technical"]
        assert adjusted["fundamental"] == scores["fundamental"]

    def test_apply_regime_filter_easing(self, mock_storage):
        """Easing regime should boost macro and fundamental scores."""
        engine = DecisionEngine(storage=mock_storage)
        scores = {"technical": 80, "macro": 60, "fundamental": 70}
        adjusted = engine.apply_regime_filter(scores, "easing")

        assert adjusted["macro"] > scores["macro"]
        assert adjusted["fundamental"] > scores["fundamental"]

    def test_recommend_no_scores_returns_error(self, mock_storage):
        """No scores in DB should return error."""
        mock_storage.load_scores.return_value = pd.DataFrame()
        engine = DecisionEngine(storage=mock_storage)
        result = engine.recommend("NO.JK")

        assert result["status"] == "error"
        assert "No scores" in result["message"]

    def test_recommend_with_scores(self, mock_storage):
        """Valid scores should produce recommendation with weights_used."""
        # Mock scores in DB
        scores_df = pd.DataFrame({
            "engine": ["technical", "fundamental", "macro", "global", "relationship", "sentiment"],
            "score": [75, 65, 55, 60, 50, 58],
            "as_of": ["2024-01-01"] * 6,
            "breakdown": ["{}"] * 6,
        })
        mock_storage.load_scores.return_value = scores_df
        mock_storage.load_ohlcv.return_value = pd.DataFrame(
            {"open": [100], "high": [105], "low": [95], "close": [102], "volume": [1000000]},
            index=pd.date_range("2024-01-01", periods=1),
        )

        engine = DecisionEngine(storage=mock_storage)
        result = engine.recommend("TEST.JK")

        assert result["status"] == "ok"
        rec = result["recommendation"]
        assert rec["action"] in ("BUY", "WATCHLIST", "HOLD", "AVOID")
        assert "weights_used" in rec
        assert "regime" in rec
        assert "var_95_1d" in rec
        assert "max_drawdown" in rec
