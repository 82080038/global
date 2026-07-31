"""Tests for XAI Engine — narrative explanation generation."""

import pandas as pd
from unittest.mock import MagicMock

from trading_system.xai.engine import ExplainableAIEngine


def test_xai_engine_name():
    engine = ExplainableAIEngine(storage=MagicMock())
    assert engine.name == "xai"


def test_xai_explain_no_scores():
    storage = MagicMock()
    storage.load_scores.return_value = pd.DataFrame()
    engine = ExplainableAIEngine(storage=storage)
    result = engine.explain("BBCA.JK")
    assert result["status"] == "error"


def test_xai_explain_with_scores():
    """XAI explain requires a recommendation dict with contributing_scores."""
    storage = MagicMock()
    engine = ExplainableAIEngine(storage=storage)
    recommendation = {
        "action": "BUY",
        "conviction_score": 68.5,
        "contributing_scores": {
            "technical": 72.5,
            "fundamental": 65.0,
            "macro": 55.0,
        },
        "risk_flags": [],
    }
    result = engine.explain("BBCA.JK", recommendation=recommendation)
    assert result["status"] == "ok"
    assert "narrative" in result
    assert len(result["narrative"]) > 0


def test_xai_explain_requires_recommendation():
    """explain() should error if no recommendation provided."""
    engine = ExplainableAIEngine(storage=MagicMock())
    result = engine.explain("BBCA.JK")
    assert result["status"] == "error"
