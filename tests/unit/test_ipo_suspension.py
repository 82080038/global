"""Tests for IPO/suspension/delisting lifecycle — schema, storage, NoTrade gates, backtest filter."""

import numpy as np
import pandas as pd
import pytest

from trading_system.ai_learning.labeling import LabelingEngine
from trading_system.analysis.no_trade import NoTradeConfig, NoTradeEngine
from trading_system.data.storage import DataStorage


@pytest.fixture
def storage(tmp_path):
    return DataStorage(db_path=tmp_path / "test_ipo.db")


class TestInstrumentStatusStorage:
    """Test instrument_master with IPO fields and status tracking."""

    def test_save_and_get_instrument_status(self, storage):
        storage.save_instrument_master({
            "ticker": "IPO1.JK",
            "name": "IPO Test",
            "ipo_date": "2025-06-01",
            "ipo_price": 1000.0,
            "status": "active",
            "lock_up_end_date": "2025-12-01",
        })
        info = storage.get_instrument_status("IPO1.JK")
        assert info is not None
        assert info["ipo_date"] == "2025-06-01"
        assert info["ipo_price"] == 1000.0
        assert info["status"] == "active"
        assert info["lock_up_end_date"] == "2025-12-01"

    def test_get_instrument_status_missing_ticker(self, storage):
        assert storage.get_instrument_status("NONEXIST.JK") is None

    def test_save_instrument_status_delisted(self, storage):
        storage.save_instrument_master({
            "ticker": "DEAD.JK",
            "name": "Delisted Co",
            "listing_date": "2020-01-01",
            "delisting_date": "2025-03-01",
            "status": "delisted",
            "is_active": 0,
        })
        info = storage.get_instrument_status("DEAD.JK")
        assert info["status"] == "delisted"
        assert info["delisting_date"] == "2025-03-01"

    def test_is_tradeable_before_listing(self, storage):
        storage.save_instrument_master({
            "ticker": "NEW.JK",
            "ipo_date": "2025-06-01",
            "status": "active",
        })
        assert storage.is_tradeable("NEW.JK", as_of="2025-05-31") is False
        assert storage.is_tradeable("NEW.JK", as_of="2025-06-01") is True

    def test_is_tradeable_after_delisting(self, storage):
        storage.save_instrument_master({
            "ticker": "OLD.JK",
            "listing_date": "2020-01-01",
            "delisting_date": "2025-03-01",
            "status": "delisted",
        })
        assert storage.is_tradeable("OLD.JK", as_of="2025-03-01") is False
        assert storage.is_tradeable("OLD.JK", as_of="2025-02-28") is True

    def test_is_tradeable_unknown_ticker(self, storage):
        assert storage.is_tradeable("UNKNOWN.JK") is True

    def test_load_active_tickers_at_date(self, storage):
        storage.save_instrument_master({
            "ticker": "A.JK", "listing_date": "2020-01-01", "status": "active",
        })
        storage.save_instrument_master({
            "ticker": "B.JK", "listing_date": "2025-06-01", "status": "active",
        })
        storage.save_instrument_master({
            "ticker": "C.JK", "listing_date": "2019-01-01",
            "delisting_date": "2024-12-31", "status": "delisted",
        })
        active = storage.load_active_tickers_at_date("2025-01-15")
        assert "A.JK" in active
        assert "B.JK" not in active  # not yet listed
        assert "C.JK" not in active  # delisted


class TestTradingSuspensions:
    """Test trading_suspensions table operations."""

    def test_save_and_load_suspension(self, storage):
        storage.save_suspension({
            "ticker": "SUSP.JK",
            "suspend_date": "2025-01-15",
            "resume_date": "2025-01-20",
            "reason": "significant price movement",
            "suspension_type": "auto",
        })
        records = storage.load_suspensions("SUSP.JK")
        assert len(records) == 1
        assert records[0]["ticker"] == "SUSP.JK"
        assert records[0]["suspend_date"] == "2025-01-15"
        assert records[0]["resume_date"] == "2025-01-20"

    def test_load_all_suspensions(self, storage):
        storage.save_suspension({"ticker": "A.JK", "suspend_date": "2025-01-01"})
        storage.save_suspension({"ticker": "B.JK", "suspend_date": "2025-02-01"})
        all_s = storage.load_suspensions()
        assert len(all_s) == 2

    def test_load_active_suspensions(self, storage):
        storage.save_suspension({
            "ticker": "A.JK",
            "suspend_date": "2025-01-01",
            "resume_date": "2025-01-10",
        })
        storage.save_suspension({
            "ticker": "B.JK",
            "suspend_date": "2025-01-01",
            "resume_date": None,
        })
        active = storage.load_active_suspensions(as_of="2025-01-15")
        assert len(active) == 1
        assert active[0]["ticker"] == "B.JK"

    def test_is_tradeable_during_suspension(self, storage):
        storage.save_instrument_master({
            "ticker": "SUSP.JK",
            "listing_date": "2020-01-01",
            "status": "active",
        })
        storage.save_suspension({
            "ticker": "SUSP.JK",
            "suspend_date": "2025-01-15",
            "resume_date": "2025-01-20",
        })
        assert storage.is_tradeable("SUSP.JK", as_of="2025-01-16") is False
        assert storage.is_tradeable("SUSP.JK", as_of="2025-01-20") is True
        assert storage.is_tradeable("SUSP.JK", as_of="2025-01-14") is True


class TestNoTradeGates:
    """Test new NoTradeEngine gates: DELISTED, IPO_LOCKUP, SUSPENDED."""

    def _base_signal(self):
        return {
            "instrument_id": 1,
            "symbol": "TEST.JK",
            "confidence": 0.8,
            "composite_alpha": 0.5,
        }

    def test_delisted_gate_blocks_trade(self):
        engine = NoTradeEngine()
        result = engine.evaluate(
            alpha_signal=self._base_signal(),
            regime_state="risk_on",
            instrument_status={"status": "delisted", "ipo_date": None, "lock_up_end_date": None},
        )
        assert result.decision == "NO_TRADE"
        assert "DELISTED" in result.gates_failed

    def test_ipo_lockup_gate_blocks_trade(self):
        engine = NoTradeEngine()
        result = engine.evaluate(
            alpha_signal=self._base_signal(),
            regime_state="risk_on",
            instrument_status={
                "status": "active",
                "ipo_date": "2025-06-01",
                "lock_up_end_date": "2099-12-31",
            },
        )
        assert result.decision == "NO_TRADE"
        assert "IPO_LOCKUP" in result.gates_failed

    def test_ipo_insufficient_history_gate(self):
        engine = NoTradeEngine(NoTradeConfig(ipo_min_history_days=20))
        result = engine.evaluate(
            alpha_signal=self._base_signal(),
            regime_state="risk_on",
            bars_history=10,
            instrument_status={
                "status": "active",
                "ipo_date": "2025-06-01",
                "lock_up_end_date": None,
            },
        )
        assert result.decision == "NO_TRADE"
        assert "IPO_INSUFFICIENT_HISTORY" in result.gates_failed

    def test_ipo_sufficient_history_proceeds(self):
        engine = NoTradeEngine(NoTradeConfig(ipo_min_history_days=20))
        result = engine.evaluate(
            alpha_signal=self._base_signal(),
            regime_state="risk_on",
            bars_history=100,
            instrument_status={
                "status": "active",
                "ipo_date": "2025-06-01",
                "lock_up_end_date": None,
            },
        )
        assert "IPO_LOCKUP" in result.gates_passed

    def test_suspended_gate_blocks_trade(self):
        engine = NoTradeEngine()
        result = engine.evaluate(
            alpha_signal=self._base_signal(),
            regime_state="risk_on",
            active_suspensions=[{"reason": "price movement", "suspend_date": "2025-01-01"}],
        )
        assert result.decision == "NO_TRADE"
        assert "SUSPENDED" in result.gates_failed

    def test_no_status_info_proceeds(self):
        engine = NoTradeEngine()
        result = engine.evaluate(
            alpha_signal=self._base_signal(),
            regime_state="risk_on",
        )
        assert result.decision == "PROCEED"
        assert "DELISTED" in result.gates_passed
        assert "IPO_LOCKUP" in result.gates_passed
        assert "SUSPENDED" in result.gates_passed


class TestBacktestSurvivorshipFilter:
    """Test backtest engine filters OHLCV by listing/delisting/suspension dates."""

    def test_backtest_filters_pre_ipo_data(self, storage):
        from trading_system.backtest.engine import BacktestEngine
        from trading_system.backtest.strategies import BuyAndHold

        # Save OHLCV starting 2024-01-01
        dates = pd.date_range("2024-01-01", periods=100, freq="B")
        df = pd.DataFrame({
            "ticker": "IPO.JK", "asset_class": "equity", "exchange": "IDX",
            "timestamp": dates.strftime("%Y-%m-%d"), "timeframe": "1d",
            "open": 100.0, "high": 105.0, "low": 95.0, "close": 100.0,
            "volume": 1_000_000.0, "adjusted_close": 100.0,
            "source": "test", "ingested_at": "2024-01-01", "data_quality_score": None,
        })
        storage.save_ohlcv(df)

        # Set IPO date to 2024-03-01 (midway through data)
        storage.save_instrument_master({
            "ticker": "IPO.JK",
            "ipo_date": "2024-03-01",
            "status": "active",
        })

        engine = BacktestEngine(storage=storage)
        result = engine.run("IPO.JK", BuyAndHold(), survivorship_free=True)
        assert result["status"] == "ok"

    def test_backtest_filters_suspension_period(self, storage):
        from trading_system.backtest.engine import BacktestEngine
        from trading_system.backtest.strategies import BuyAndHold

        dates = pd.date_range("2024-01-01", periods=100, freq="B")
        df = pd.DataFrame({
            "ticker": "SUSP.JK", "asset_class": "equity", "exchange": "IDX",
            "timestamp": dates.strftime("%Y-%m-%d"), "timeframe": "1d",
            "open": 100.0, "high": 105.0, "low": 95.0, "close": 100.0,
            "volume": 1_000_000.0, "adjusted_close": 100.0,
            "source": "test", "ingested_at": "2024-01-01", "data_quality_score": None,
        })
        storage.save_ohlcv(df)

        storage.save_instrument_master({
            "ticker": "SUSP.JK",
            "listing_date": "2023-01-01",
            "status": "active",
        })
        storage.save_suspension({
            "ticker": "SUSP.JK",
            "suspend_date": "2024-02-01",
            "resume_date": "2024-02-15",
        })

        engine = BacktestEngine(storage=storage)
        result = engine.run("SUSP.JK", BuyAndHold(), survivorship_free=True)
        assert result["status"] == "ok"


class TestLabelingNonTradeableMask:
    """Test ML labeling masks non-tradeable periods."""

    def test_non_tradeable_mask_sets_nan(self):
        dates = pd.date_range("2024-01-01", periods=100, freq="B")
        df = pd.DataFrame({
            "open": 100.0, "high": 105.0, "low": 95.0, "close": 100.0,
        }, index=dates)

        mask = pd.Series(False, index=dates)
        mask.iloc[20:25] = True  # 5 non-tradeable bars

        engine = LabelingEngine()
        labels = engine.compute(df, non_tradeable_mask=mask)

        fwd = labels["forward_return"]
        # Masked bars should be NaN
        assert fwd.iloc[20:25].isna().all()
        # Bars well after the mask should still have valid labels
        assert fwd.iloc[50:90].notna().any()

    def test_no_mask_returns_all_labels(self):
        dates = pd.date_range("2024-01-01", periods=50, freq="B")
        df = pd.DataFrame({
            "open": 100.0, "high": 105.0, "low": 95.0, "close": 100.0,
        }, index=dates)

        engine = LabelingEngine()
        labels = engine.compute(df)
        assert labels["forward_return"].notna().sum() > 0
