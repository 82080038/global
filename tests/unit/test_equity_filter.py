"""Regression tests for equity-only filtering in downstream engines.

Ensures that list_active_equity_tickers returns only active equity stocks
with .JK suffix, and that downstream engines use this method instead of
the unfiltered list_tickers.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestListActiveEquityTickers:
    """Tests for DataStorage.list_active_equity_tickers()."""

    def test_returns_only_jk_tickers(self):
        """All returned tickers should have .JK suffix."""
        from trading_system.data.storage import DataStorage

        storage = DataStorage()
        tickers = storage.list_active_equity_tickers()
        assert len(tickers) > 0
        assert all(t.endswith(".JK") for t in tickers), "All equity tickers should end with .JK"

    def test_excludes_non_equity(self):
        """Non-equity tickers (forex, index, commodity, ETF) should NOT be in the list."""
        from trading_system.data.storage import DataStorage

        storage = DataStorage()
        tickers = set(storage.list_active_equity_tickers())
        all_tickers = set(storage.list_tickers())
        non_equity = all_tickers - tickers

        # Known non-equity tickers that should be excluded
        known_non_equity = {"^GSPC", "^JKSE", "CL=F", "IDR=X", "DX-Y.NYB"}
        assert known_non_equity.issubset(non_equity), f"Missing non-equity exclusions: {known_non_equity - non_equity}"

    def test_excludes_delisted(self):
        """Delisted tickers should NOT be in the active equity list."""
        from trading_system.data.storage import DataStorage

        storage = DataStorage()
        active = set(storage.list_active_equity_tickers())

        with storage._connect() as conn:
            delisted = conn.execute(
                "SELECT ticker FROM instrument_master WHERE asset_class = 'equity' AND is_active = 0"
            ).fetchall()
        delisted_tickers = {r[0] for r in delisted}
        # Delisted tickers in instrument_master are bare (no .JK), so check both forms
        leaked = {t for t in active if t.replace(".JK", "") in delisted_tickers}
        assert not leaked, f"Delisted tickers found in active list: {leaked}"


class TestDownstreamEnginesUseEquityFilter:
    """Verify that downstream engines call list_active_equity_tickers, not list_tickers."""

    def test_factor_engine_uses_equity_filter(self):
        """FactorEngine.compute() with no tickers should call list_active_equity_tickers."""
        from trading_system.analysis.factor_engine import FactorEngine

        storage = MagicMock()
        storage.list_active_equity_tickers.return_value = []
        storage.list_tickers.return_value = ["SHOULD_NOT_BE_USED"]

        engine = FactorEngine(storage=storage)
        engine.compute()

        storage.list_active_equity_tickers.assert_called_once()
        storage.list_tickers.assert_not_called()

    def test_ai_learning_uses_equity_filter(self):
        """AILearningEngine.train_linear_regression() with no ticker should call list_active_equity_tickers."""
        from trading_system.ai_learning.engine import AILearningEngine

        storage = MagicMock()
        storage.list_active_equity_tickers.return_value = []
        storage.list_tickers.return_value = ["SHOULD_NOT_BE_USED"]

        engine = AILearningEngine(storage=storage)
        engine.train_linear_regression()

        storage.list_active_equity_tickers.assert_called_once()
        storage.list_tickers.assert_not_called()

    def test_monitoring_uses_equity_filter(self):
        """MonitoringEngine.health() should call list_active_equity_tickers."""
        from trading_system.monitoring.engine import MonitoringEngine

        storage = MagicMock()
        storage.get_source_health.return_value = MagicMock(empty=True)
        storage.list_active_equity_tickers.return_value = []
        storage.list_tickers.return_value = ["SHOULD_NOT_BE_USED"]
        storage.load_scores.return_value = MagicMock(empty=True)

        engine = MonitoringEngine(storage=storage)
        engine.health()

        storage.list_active_equity_tickers.assert_called_once()
        storage.list_tickers.assert_not_called()
