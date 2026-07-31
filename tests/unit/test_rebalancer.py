"""Unit tests for PortfolioRebalancer."""

import json
import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from trading_system.data.storage import DataStorage
from trading_system.portfolio.rebalancer import PortfolioRebalancer


@pytest.fixture
def temp_storage():
    """Create a temporary DataStorage with test OHLCV data for 3 tickers."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_rebalance.db"
        storage = DataStorage(db_path=db_path)

        dates = pd.date_range("2024-01-01", periods=30, freq="D")
        for ticker, base_price in [("BBCA.JK", 8000), ("TLKM.JK", 3500), ("ASII.JK", 6000)]:
            df = pd.DataFrame({
                "ticker": [ticker] * 30,
                "asset_class": ["stock"] * 30,
                "exchange": ["IDX"] * 30,
                "timestamp": [d.isoformat() for d in dates],
                "timeframe": ["1d"] * 30,
                "open": [base_price + i * 10 for i in range(30)],
                "high": [base_price + 50 + i * 10 for i in range(30)],
                "low": [base_price - 50 + i * 10 for i in range(30)],
                "close": [base_price + i * 10 for i in range(30)],
                "volume": [1_000_000 + i * 1000 for i in range(30)],
                "adjusted_close": [base_price + i * 10 for i in range(30)],
                "source": ["test"] * 30,
                "ingested_at": [dates[0].isoformat()] * 30,
                "data_quality_score": [95.0] * 30,
            })
            storage.save_ohlcv(df)
        yield storage


class TestPortfolioRebalancer:

    def test_init_defaults(self, temp_storage):
        """Rebalancer initializes disabled by default."""
        os.environ.pop("REBALANCE_ENABLED", None)
        rebalancer = PortfolioRebalancer(storage=temp_storage)
        assert rebalancer.rebalance_enabled is False
        assert rebalancer.rebalance_frequency == "monthly"

    def test_init_with_target_weights(self, temp_storage):
        """Rebalancer loads target weights from env."""
        os.environ["REBALANCE_ENABLED"] = "true"
        os.environ["REBALANCE_TARGET_WEIGHTS"] = json.dumps({
            "BBCA.JK": 0.4, "TLKM.JK": 0.3, "ASII.JK": 0.3
        })
        rebalancer = PortfolioRebalancer(storage=temp_storage)
        assert rebalancer.rebalance_enabled is True
        assert rebalancer.target_weights["BBCA.JK"] == 0.4
        os.environ.pop("REBALANCE_ENABLED", None)
        os.environ.pop("REBALANCE_TARGET_WEIGHTS", None)

    def test_init_invalid_json(self, temp_storage):
        """Invalid JSON in env var results in empty target weights."""
        os.environ["REBALANCE_TARGET_WEIGHTS"] = "not json"
        rebalancer = PortfolioRebalancer(storage=temp_storage)
        assert rebalancer.target_weights == {}
        os.environ.pop("REBALANCE_TARGET_WEIGHTS", None)

    def test_get_latest_price(self, temp_storage):
        """Latest price is retrieved from OHLCV."""
        rebalancer = PortfolioRebalancer(storage=temp_storage)
        price = rebalancer._get_latest_price("BBCA.JK")
        assert price is not None
        assert price == pytest.approx(8000 + 29 * 10, rel=0.01)

    def test_get_current_portfolio_value_empty(self, temp_storage):
        """Portfolio value is 0 when no positions."""
        rebalancer = PortfolioRebalancer(storage=temp_storage)
        assert rebalancer.get_current_portfolio_value() == 0

    def test_get_current_portfolio_value_with_positions(self, temp_storage):
        """Portfolio value is calculated from positions."""
        rebalancer = PortfolioRebalancer(storage=temp_storage)
        # Create positions
        temp_storage.save_position("BBCA.JK", 1000, 8000)
        temp_storage.save_position("TLKM.JK", 2000, 3500)

        value = rebalancer.get_current_portfolio_value()
        # BBCA: 1000 * (8000 + 290) = 8,290,000
        # TLKM: 2000 * (3500 + 290) = 7,580,000
        assert value > 0

    def test_get_current_weights(self, temp_storage):
        """Current weights are calculated proportionally."""
        rebalancer = PortfolioRebalancer(storage=temp_storage)
        temp_storage.save_position("BBCA.JK", 1000, 8000)
        temp_storage.save_position("TLKM.JK", 2000, 3500)

        weights = rebalancer.get_current_weights()
        assert "BBCA.JK" in weights
        assert "TLKM.JK" in weights
        assert sum(weights.values()) == pytest.approx(1.0, rel=0.01)

    def test_get_target_quantity(self, temp_storage):
        """Target quantity is calculated from weight and rounded to lot."""
        rebalancer = PortfolioRebalancer(storage=temp_storage)
        rebalancer.target_weights = {"BBCA.JK": 0.5}
        qty = rebalancer._get_target_quantity(100_000_000, "BBCA.JK", 8000)
        # 50,000,000 / 8000 = 6250 -> round to 6200
        assert qty > 0
        assert qty % 100 == 0

    def test_run_rebalance_disabled(self, temp_storage):
        """Rebalancing does nothing when disabled."""
        os.environ.pop("REBALANCE_ENABLED", None)
        rebalancer = PortfolioRebalancer(storage=temp_storage)
        results = rebalancer.run_rebalance()
        assert results == []

    def test_run_rebalance_no_target_weights(self, temp_storage):
        """Rebalancing does nothing without target weights."""
        os.environ["REBALANCE_ENABLED"] = "true"
        os.environ.pop("REBALANCE_TARGET_WEIGHTS", None)
        rebalancer = PortfolioRebalancer(storage=temp_storage)
        rebalancer.target_weights = {}
        results = rebalancer.run_rebalance()
        assert results == []
        os.environ.pop("REBALANCE_ENABLED", None)

    def test_run_rebalance_no_portfolio(self, temp_storage):
        """Rebalancing does nothing with zero portfolio value."""
        os.environ["REBALANCE_ENABLED"] = "true"
        rebalancer = PortfolioRebalancer(storage=temp_storage)
        rebalancer.rebalance_enabled = True
        rebalancer.target_weights = {"BBCA.JK": 0.4, "TLKM.JK": 0.3, "ASII.JK": 0.3}
        results = rebalancer.run_rebalance()
        assert results == []
        os.environ.pop("REBALANCE_ENABLED", None)

    def test_run_rebalance_creates_positions(self, temp_storage):
        """Rebalancing creates positions when portfolio has value."""
        rebalancer = PortfolioRebalancer(storage=temp_storage)
        rebalancer.rebalance_enabled = True
        rebalancer.target_weights = {"BBCA.JK": 0.5, "TLKM.JK": 0.5}

        # Create initial position so portfolio has value
        temp_storage.save_position("BBCA.JK", 1000, 8000)

        results = rebalancer.run_rebalance()
        # Should buy TLKM to reach 50/50 target
        tlkm_pos = temp_storage.get_open_position("TLKM.JK")
        assert tlkm_pos is not None
        assert tlkm_pos["quantity"] > 0

    def test_run_rebalance_sells_excess(self, temp_storage):
        """Rebalancing sells when position exceeds target."""
        rebalancer = PortfolioRebalancer(storage=temp_storage)
        rebalancer.rebalance_enabled = True
        rebalancer.target_weights = {"BBCA.JK": 0.2, "TLKM.JK": 0.8}

        # Create overweight BBCA position
        temp_storage.save_position("BBCA.JK", 5000, 8000)
        # Create underweight TLKM position
        temp_storage.save_position("TLKM.JK", 100, 3500)

        results = rebalancer.run_rebalance()

        # BBCA should be reduced (sold)
        bbca_after = temp_storage.get_open_position("BBCA.JK")
        assert bbca_after["quantity"] < 5000

    def test_rebalance_status(self, temp_storage):
        """Rebalance status returns correct structure."""
        rebalancer = PortfolioRebalancer(storage=temp_storage)
        rebalancer.target_weights = {"BBCA.JK": 0.5, "TLKM.JK": 0.5}
        temp_storage.save_position("BBCA.JK", 1000, 8000)

        status = rebalancer.get_rebalance_status()
        assert "enabled" in status
        assert "frequency" in status
        assert "target_weights" in status
        assert "current_weights" in status
        assert "total_portfolio_value" in status
        assert "drift" in status
        assert status["target_weights"]["BBCA.JK"] == 0.5

    def test_rebalance_buy_creates_order(self, temp_storage):
        """Rebalance BUY creates an order with REBALANCE trigger."""
        rebalancer = PortfolioRebalancer(storage=temp_storage)
        result = rebalancer._execute_rebalance_buy("BBCA.JK", 100, 8000)
        assert result["status"] == "ok"
        assert result["action"] == "BUY"

        orders = temp_storage.get_orders("BBCA.JK")
        assert len(orders) == 1
        assert orders[0]["trigger"] == "REBALANCE"
        assert orders[0]["order_style"] == "REBALANCE"

    def test_rebalance_sell_creates_order(self, temp_storage):
        """Rebalance SELL creates an order and closes position."""
        rebalancer = PortfolioRebalancer(storage=temp_storage)
        # First create a position
        temp_storage.save_position("BBCA.JK", 200, 8000)
        # Then sell half
        result = rebalancer._execute_rebalance_sell("BBCA.JK", 100, 8500)
        assert result["status"] == "ok"
        assert result["action"] == "SELL"
        assert result["realized_pnl"] == pytest.approx(50000, rel=0.01)

        # Position should still be open with 100 remaining
        pos = temp_storage.get_open_position("BBCA.JK")
        assert pos is not None
        assert pos["quantity"] == 100
