"""Unit tests for RiskEngine."""

from unittest.mock import MagicMock

import pandas as pd

from trading_system.risk.engine import RiskEngine


class TestRiskEngine:

    def test_analyze_returns_ok(self, mock_storage):
        """RiskEngine.analyze should return ok status with all risk metrics."""
        engine = RiskEngine(storage=mock_storage)
        result = engine.analyze("TEST.JK")

        assert result["status"] == "ok"
        assert result["ticker"] == "TEST.JK"
        assert "last_price" in result
        assert "atr" in result
        assert "position_size" in result
        assert "stop_loss" in result
        assert "take_profit" in result
        assert "risk_flags" in result

    def test_var_computed(self, mock_storage):
        """VaR (95% and 99%) should be computed and positive."""
        engine = RiskEngine(storage=mock_storage)
        result = engine.analyze("TEST.JK")

        assert "var_95_1d" in result
        assert "var_99_1d" in result
        assert result["var_95_1d"] >= 0
        assert result["var_99_1d"] >= result["var_95_1d"]  # 99% VaR >= 95% VaR

    def test_cvar_computed(self, mock_storage):
        """CVaR (Expected Shortfall) should be computed."""
        engine = RiskEngine(storage=mock_storage)
        result = engine.analyze("TEST.JK")

        assert "cvar_95_1d" in result
        assert result["cvar_95_1d"] >= 0

    def test_max_drawdown_computed(self, mock_storage):
        """Max drawdown should be computed and <= 0."""
        engine = RiskEngine(storage=mock_storage)
        result = engine.analyze("TEST.JK")

        assert "max_drawdown" in result
        assert result["max_drawdown"] <= 0

    def test_daily_max_loss_computed(self, mock_storage):
        """Daily max loss should be computed."""
        engine = RiskEngine(storage=mock_storage)
        result = engine.analyze("TEST.JK")

        assert "daily_max_loss" in result
        assert result["daily_max_loss"] <= 0

    def test_empty_data_returns_error(self):
        """Empty OHLCV should return error."""
        mock_storage = MagicMock()
        mock_storage.load_ohlcv.return_value = pd.DataFrame()

        engine = RiskEngine(storage=mock_storage)
        result = engine.analyze("EMPTY.JK")

        assert result["status"] == "error"
        assert "No OHLCV" in result["message"]

    def test_compute_var_empty_returns_zero(self):
        """Empty returns should give 0 VaR."""
        engine = RiskEngine(storage=MagicMock())
        var_95, var_99 = engine._compute_var(pd.Series(dtype=float), 100.0)
        assert var_95 == 0.0
        assert var_99 == 0.0

    def test_compute_max_drawdown_empty(self):
        """Empty close series should give 0 max drawdown."""
        engine = RiskEngine(storage=MagicMock())
        mdd = engine._compute_max_drawdown(pd.Series(dtype=float))
        assert mdd == 0.0

    def test_position_size_capped(self, mock_storage):
        """Position size should not exceed 10% of capital."""
        engine = RiskEngine(storage=mock_storage)
        result = engine.analyze("TEST.JK", capital=1_000_000_000)

        assert result["position_size"] <= 0.1

    def test_annualized_volatility(self, mock_storage):
        """Annualized volatility should be computed and positive."""
        engine = RiskEngine(storage=mock_storage)
        result = engine.analyze("TEST.JK")

        assert "annualized_volatility" in result
        assert result["annualized_volatility"] > 0
