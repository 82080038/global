"""Tests for DataStorage — system_state key-value store & order realized_pnl (§3.4)."""

import pytest

from trading_system.data.storage import DataStorage


@pytest.fixture
def storage(tmp_path):
    return DataStorage(db_path=tmp_path / "test.db")


def test_get_state_missing_key_returns_none(storage):
    assert storage.get_state("nonexistent") is None


def test_set_and_get_state(storage):
    storage.set_state("execution_halted_date", "2026-07-31")
    assert storage.get_state("execution_halted_date") == "2026-07-31"


def test_set_state_overwrites_existing_value(storage):
    storage.set_state("k", "v1")
    storage.set_state("k", "v2")
    assert storage.get_state("k") == "v2"


def test_save_order_persists_realized_pnl(storage):
    order_id = storage.save_order(
        ticker="TEST.JK", order_type="SELL", quantity=100, price=120,
        fee=100, trigger="SIGNAL", realized_pnl=2000.0,
    )
    orders = storage.get_orders(ticker="TEST.JK")
    assert len(orders) == 1
    assert orders[0]["id"] == order_id
    assert orders[0]["realized_pnl"] == 2000.0


def test_save_order_default_realized_pnl_is_zero(storage):
    storage.save_order(ticker="TEST.JK", order_type="BUY", quantity=100, price=100)
    orders = storage.get_orders(ticker="TEST.JK")
    assert orders[0]["realized_pnl"] == 0
