"""Unit tests for broker adapter abstraction."""

from __future__ import annotations

import os

import pytest

from trading_system.execution.broker_adapter import (
    BrokerAccount,
    BrokerOrder,
    BrokerOrderResult,
    BrokerPosition,
    MockBrokerAdapter,
    get_broker_adapter,
    list_available_brokers,
)


class TestMockBrokerAdapter:
    """Tests for MockBrokerAdapter."""

    def test_authenticate_returns_true(self):
        adapter = MockBrokerAdapter()
        assert adapter.authenticate() is True

    def test_initial_cash_balance(self):
        adapter = MockBrokerAdapter()
        adapter.authenticate()
        assert adapter.get_cash_balance() == 100_000_000.0

    def test_get_account_returns_correct_structure(self):
        adapter = MockBrokerAdapter()
        account = adapter.get_account()
        assert isinstance(account, BrokerAccount)
        assert account.currency == "IDR"
        assert account.cash_balance == 100_000_000.0
        assert account.total_equity >= 0
        assert account.buying_power >= 0

    def test_place_buy_order_succeeds(self):
        adapter = MockBrokerAdapter()
        order = BrokerOrder(
            ticker="BBCA.JK",
            action="buy",
            shares=100,
            price=8000.0,
        )
        result = adapter.place_order(order)
        assert result.status == "ok"
        assert result.broker_order_id is not None
        assert result.filled_price == 8000.0
        assert result.filled_shares == 100
        assert result.fees > 0

    def test_buy_order_creates_position(self):
        adapter = MockBrokerAdapter()
        order = BrokerOrder(
            ticker="TLKM.JK",
            action="buy",
            shares=200,
            price=3000.0,
        )
        adapter.place_order(order)
        position = adapter.get_position("TLKM.JK")
        assert position is not None
        assert position.ticker == "TLKM.JK"
        assert position.shares == 200
        assert position.avg_price == 3000.0

    def test_buy_order_reduces_cash(self):
        adapter = MockBrokerAdapter()
        initial_cash = adapter.get_cash_balance()
        order = BrokerOrder(
            ticker="BBCA.JK",
            action="buy",
            shares=100,
            price=8000.0,
        )
        adapter.place_order(order)
        new_cash = adapter.get_cash_balance()
        assert new_cash < initial_cash
        # Cash should decrease by (price * shares + fees)
        expected_cost = 8000.0 * 100 * 1.0015
        assert abs(new_cash - (initial_cash - expected_cost)) < 1.0

    def test_sell_order_closes_position(self):
        adapter = MockBrokerAdapter()
        # Buy first
        buy_order = BrokerOrder(
            ticker="BBCA.JK",
            action="buy",
            shares=100,
            price=8000.0,
        )
        adapter.place_order(buy_order)

        # Sell
        sell_order = BrokerOrder(
            ticker="BBCA.JK",
            action="sell",
            shares=100,
            price=8100.0,
        )
        result = adapter.place_order(sell_order)
        assert result.status == "ok"
        assert result.filled_price == 8100.0

        # Position should be gone
        position = adapter.get_position("BBCA.JK")
        assert position is None

    def test_sell_without_position_rejected(self):
        adapter = MockBrokerAdapter()
        sell_order = BrokerOrder(
            ticker="BBCA.JK",
            action="sell",
            shares=100,
            price=8000.0,
        )
        result = adapter.place_order(sell_order)
        assert result.status == "rejected"

    def test_insufficient_cash_rejected(self):
        adapter = MockBrokerAdapter()
        order = BrokerOrder(
            ticker="BBCA.JK",
            action="buy",
            shares=100_000,  # Way too many
            price=8000.0,
        )
        result = adapter.place_order(order)
        assert result.status == "rejected"

    def test_partial_sell_updates_position(self):
        adapter = MockBrokerAdapter()
        # Buy 200 shares
        buy_order = BrokerOrder(
            ticker="BBCA.JK",
            action="buy",
            shares=200,
            price=8000.0,
        )
        adapter.place_order(buy_order)

        # Sell 50 shares
        sell_order = BrokerOrder(
            ticker="BBCA.JK",
            action="sell",
            shares=50,
            price=8100.0,
        )
        adapter.place_order(sell_order)

        position = adapter.get_position("BBCA.JK")
        assert position is not None
        assert position.shares == 150

    def test_get_all_positions(self):
        adapter = MockBrokerAdapter()
        adapter.place_order(BrokerOrder(ticker="BBCA.JK", action="buy", shares=100, price=8000.0))
        adapter.place_order(BrokerOrder(ticker="TLKM.JK", action="buy", shares=200, price=3000.0))

        positions = adapter.get_all_positions()
        assert len(positions) == 2
        tickers = {p.ticker for p in positions}
        assert "BBCA.JK" in tickers
        assert "TLKM.JK" in tickers

    def test_cancel_order_not_supported(self):
        adapter = MockBrokerAdapter()
        result = adapter.cancel_order("MOCK-000001")
        assert result.status == "error"

    def test_get_order_status_existing(self):
        adapter = MockBrokerAdapter()
        order = BrokerOrder(ticker="BBCA.JK", action="buy", shares=100, price=8000.0)
        placed = adapter.place_order(order)
        status = adapter.get_order_status(placed.broker_order_id)
        assert status.status == "ok"

    def test_get_order_status_not_found(self):
        adapter = MockBrokerAdapter()
        status = adapter.get_order_status("NONEXISTENT")
        assert status.status == "error"


class TestBrokerRegistry:
    """Tests for broker adapter registry."""

    def test_list_available_brokers_includes_mock(self):
        brokers = list_available_brokers()
        assert "mock" in brokers

    def test_get_broker_adapter_default_is_mock(self):
        # Clear env var to test default
        old = os.environ.pop("BROKER_ADAPTER", None)
        try:
            adapter = get_broker_adapter()
            assert adapter.name == "mock"
        finally:
            if old is not None:
                os.environ["BROKER_ADAPTER"] = old

    def test_get_broker_adapter_by_name(self):
        adapter = get_broker_adapter("mock")
        assert isinstance(adapter, MockBrokerAdapter)

    def test_get_broker_adapter_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown broker adapter"):
            get_broker_adapter("nonexistent_broker")

    def test_get_broker_adapter_from_env(self):
        os.environ["BROKER_ADAPTER"] = "mock"
        try:
            adapter = get_broker_adapter()
            assert adapter.name == "mock"
        finally:
            del os.environ["BROKER_ADAPTER"]
