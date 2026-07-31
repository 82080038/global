"""Regression tests for AutomatedExecutionEngine — daily loss limit (§3.4)."""

import os
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

from trading_system.execution.automated import AutomatedExecutionEngine


@pytest.fixture
def engine(mock_storage, monkeypatch):
    monkeypatch.setenv("DAILY_LOSS_LIMIT", "1000000")
    mock_storage.get_state.return_value = None
    eng = AutomatedExecutionEngine(storage=mock_storage)
    eng.daily_loss_limit = 1_000_000
    return eng


def test_no_limit_set_never_halts(mock_storage):
    eng = AutomatedExecutionEngine(storage=mock_storage)
    eng.daily_loss_limit = 0
    assert eng._check_daily_loss_limit() is False


def test_uses_realized_pnl_column_not_avg_buy_estimate(engine, mock_storage):
    """Loss harus dihitung dari kolom realized_pnl langsung, bukan estimasi
    rata-rata harga BUY historis yang bisa jauh meleset."""
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date().isoformat()

    mock_storage.get_orders.return_value = [
        {"ticker": "TEST.JK", "order_type": "SELL", "realized_pnl": -2_000_000,
         "created_at": f"{today}T10:00:00+00:00", "price": 100, "quantity": 100},
        # Old BUY at a very different price — must NOT affect the loss calc.
        {"ticker": "TEST.JK", "order_type": "BUY", "realized_pnl": 0,
         "created_at": "2020-01-01T10:00:00+00:00", "price": 50000, "quantity": 100},
    ]

    assert engine._check_daily_loss_limit() is True
    mock_storage.set_state.assert_called_once()


def test_halt_persisted_and_checked_on_next_call(engine, mock_storage):
    """Setelah limit terpicu, panggilan berikutnya di hari yang sama tetap halt
    tanpa perlu menghitung ulang order (state dipersist di system_state)."""
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date().isoformat()
    mock_storage.get_state.return_value = today

    assert engine._check_daily_loss_limit() is True
    mock_storage.get_orders.assert_not_called()


def test_no_halt_when_loss_within_limit(engine, mock_storage):
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date().isoformat()
    mock_storage.get_orders.return_value = [
        {"ticker": "TEST.JK", "order_type": "SELL", "realized_pnl": -500_000,
         "created_at": f"{today}T10:00:00+00:00", "price": 100, "quantity": 100},
    ]
    assert engine._check_daily_loss_limit() is False


def test_execute_sell_persists_realized_pnl(mock_storage):
    """_execute_sell harus meneruskan realized_pnl ke storage.save_order."""
    mock_storage.get_state.return_value = None
    mock_storage.save_order.return_value = 1
    mock_storage.save_position.return_value = 1
    mock_storage.update_position = MagicMock()

    eng = AutomatedExecutionEngine(storage=mock_storage)
    position = {"id": 1, "ticker": "TEST.JK", "quantity": 100, "avg_entry_price": 100}
    eng._execute_sell("TEST.JK", 100, 120, trigger="SIGNAL", position=position)

    _, kwargs = mock_storage.save_order.call_args
    assert kwargs["realized_pnl"] == pytest.approx((120 - 100) * 100)
