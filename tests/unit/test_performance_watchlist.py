"""Unit tests for PerformanceAnalytics, Daily Loss Limit, and Watchlist."""

import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from trading_system.data.storage import DataStorage
from trading_system.portfolio.performance import PerformanceAnalytics
from trading_system.execution.automated import AutomatedExecutionEngine


@pytest.fixture
def temp_storage():
    """Create a temporary DataStorage with test OHLCV data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_perf.db"
        storage = DataStorage(db_path=db_path)

        dates = pd.date_range("2024-01-01", periods=30, freq="D")
        for ticker, base_price in [("BBCA.JK", 8000), ("TLKM.JK", 3500)]:
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


# ==================== PERFORMANCE ANALYTICS ====================
class TestPerformanceAnalytics:

    def test_init_defaults(self, temp_storage):
        """PerformanceAnalytics initializes with default capital."""
        os.environ.pop("TRADING_CAPITAL", None)
        analytics = PerformanceAnalytics(storage=temp_storage)
        assert analytics.initial_capital == 100_000_000

    def test_init_custom_capital(self, temp_storage):
        """PerformanceAnalytics reads custom capital from env."""
        os.environ["TRADING_CAPITAL"] = "50000000"
        analytics = PerformanceAnalytics(storage=temp_storage)
        assert analytics.initial_capital == 50_000_000
        os.environ.pop("TRADING_CAPITAL", None)

    def test_compute_equity_no_positions(self, temp_storage):
        """Equity equals initial capital when no positions or orders."""
        analytics = PerformanceAnalytics(storage=temp_storage)
        equity = analytics.compute_equity()
        assert equity == pytest.approx(100_000_000, rel=0.01)

    def test_compute_equity_with_positions(self, temp_storage):
        """Equity includes positions market value."""
        analytics = PerformanceAnalytics(storage=temp_storage)
        temp_storage.save_position("BBCA.JK", 100, 8000)
        # Buy order reduces cash
        temp_storage.save_order("BBCA.JK", "BUY", 100, 8000)
        equity = analytics.compute_equity()
        # Latest BBCA price = 8000 + 29*10 = 8290
        # Cash = 100M - (100*8000) = 99.2M
        # Positions = 100 * 8290 = 829,000
        # Equity = 99,200,000 + 829,000 = 100,029,000
        assert equity > 100_000_000

    def test_save_daily_snapshot(self, temp_storage):
        """Snapshot is saved to DB."""
        analytics = PerformanceAnalytics(storage=temp_storage)
        temp_storage.save_position("BBCA.JK", 100, 8000)
        temp_storage.save_order("BBCA.JK", "BUY", 100, 8000)
        equity = analytics.save_daily_snapshot()
        assert equity > 0

        snapshots = temp_storage.get_equity_snapshots()
        assert len(snapshots) == 1
        assert snapshots[0]["equity"] > 0

    def test_get_performance_empty(self, temp_storage):
        """Performance returns zeros when no data."""
        analytics = PerformanceAnalytics(storage=temp_storage)
        perf = analytics.get_performance(period="1M")
        assert perf["total_trades"] == 0
        assert perf["total_return"] == 0
        assert perf["sharpe_ratio"] == 0
        assert perf["max_drawdown"] == 0
        assert perf["win_rate"] == 0

    def test_get_performance_with_orders(self, temp_storage):
        """Performance computes metrics from orders."""
        analytics = PerformanceAnalytics(storage=temp_storage)
        # Create buy and sell orders
        temp_storage.save_order("BBCA.JK", "BUY", 100, 8000)
        temp_storage.save_order("BBCA.JK", "SELL", 100, 8500)
        # Save a snapshot
        analytics.save_daily_snapshot()

        perf = analytics.get_performance(period="ALL")
        assert perf["total_trades"] >= 2
        assert "equity_curve" in perf
        assert "current_equity" in perf

    def test_get_performance_period_filtering(self, temp_storage):
        """Performance filters by period."""
        analytics = PerformanceAnalytics(storage=temp_storage)
        temp_storage.save_order("BBCA.JK", "BUY", 100, 8000)
        analytics.save_daily_snapshot()

        for period in ["1W", "1M", "3M", "6M", "1Y", "ALL"]:
            perf = analytics.get_performance(period=period)
            assert "total_return" in perf
            assert "equity_curve" in perf


# ==================== DAILY LOSS LIMIT ====================
class TestDailyLossLimit:

    def test_no_limit_returns_false(self, temp_storage):
        """No daily loss limit set means trading continues."""
        os.environ.pop("DAILY_LOSS_LIMIT", None)
        engine = AutomatedExecutionEngine(storage=temp_storage)
        assert engine.daily_loss_limit == 0
        assert engine._check_daily_loss_limit() is False

    def test_no_sells_returns_false(self, temp_storage):
        """No sell orders today means no loss."""
        os.environ["DAILY_LOSS_LIMIT"] = "1000000"
        engine = AutomatedExecutionEngine(storage=temp_storage)
        # Only buy orders, no sells
        temp_storage.save_order("BBCA.JK", "BUY", 100, 8000)
        assert engine._check_daily_loss_limit() is False
        os.environ.pop("DAILY_LOSS_LIMIT", None)

    def test_profit_sells_returns_false(self, temp_storage):
        """Profitable sells don't trigger circuit breaker."""
        os.environ["DAILY_LOSS_LIMIT"] = "1000000"
        engine = AutomatedExecutionEngine(storage=temp_storage)
        # Buy at 8000, sell at 8500 (profit)
        temp_storage.save_order("BBCA.JK", "BUY", 100, 8000)
        temp_storage.save_order("BBCA.JK", "SELL", 100, 8500)
        assert engine._check_daily_loss_limit() is False
        os.environ.pop("DAILY_LOSS_LIMIT", None)

    def test_loss_exceeds_limit_returns_true(self, temp_storage):
        """Large loss triggers circuit breaker."""
        os.environ["DAILY_LOSS_LIMIT"] = "99999"
        engine = AutomatedExecutionEngine(storage=temp_storage)
        # Buy at 8000, sell at 7000 (loss = 100*1000 = 100,000).
        # realized_pnl diteruskan eksplisit (dihitung dari harga entry posisi
        # sebenarnya oleh _execute_sell), bukan diestimasi ulang dari rata-rata
        # semua BUY historis (§3.4 SARAN_PENGEMBANGAN.md).
        temp_storage.save_order("BBCA.JK", "BUY", 100, 8000)
        temp_storage.save_order("BBCA.JK", "SELL", 100, 7000, realized_pnl=-100_000)
        result = engine._check_daily_loss_limit()
        assert result is True
        os.environ.pop("DAILY_LOSS_LIMIT", None)

    def test_loss_within_limit_returns_false(self, temp_storage):
        """Small loss within limit doesn't trigger."""
        os.environ["DAILY_LOSS_LIMIT"] = "1000000"
        engine = AutomatedExecutionEngine(storage=temp_storage)
        # Buy at 8000, sell at 7900 (loss = 100*100 = 10,000)
        temp_storage.save_order("BBCA.JK", "BUY", 100, 8000)
        temp_storage.save_order("BBCA.JK", "SELL", 100, 7900, realized_pnl=-10_000)
        result = engine._check_daily_loss_limit()
        assert result is False
        os.environ.pop("DAILY_LOSS_LIMIT", None)

    def test_circuit_breaker_halts_run_once(self, temp_storage):
        """run_once returns circuit_breaker status when limit hit."""
        os.environ["DAILY_LOSS_LIMIT"] = "100"
        engine = AutomatedExecutionEngine(storage=temp_storage)
        temp_storage.save_order("BBCA.JK", "BUY", 100, 8000)
        temp_storage.save_order("BBCA.JK", "SELL", 100, 7000, realized_pnl=-100_000)
        results = engine.run_once(tickers=["BBCA.JK"])
        assert len(results) == 1
        assert results[0]["status"] == "circuit_breaker"
        os.environ.pop("DAILY_LOSS_LIMIT", None)


# ==================== WATCHLIST ====================
class TestWatchlist:

    def test_toggle_watchlist_new_ticker(self, temp_storage):
        """Toggle on a new ticker adds it as favorite."""
        result = temp_storage.toggle_watchlist("BBCA.JK")
        assert result is True
        items = temp_storage.get_watchlist()
        assert len(items) == 1
        assert items[0]["ticker"] == "BBCA.JK"

    def test_toggle_watchlist_off(self, temp_storage):
        """Toggle off unfavorites a ticker."""
        temp_storage.toggle_watchlist("BBCA.JK")
        result = temp_storage.toggle_watchlist("BBCA.JK")
        assert result is False
        items = temp_storage.get_watchlist(favorites_only=True)
        assert len(items) == 0

    def test_toggle_watchlist_back_on(self, temp_storage):
        """Toggle back on re-favorites a ticker."""
        temp_storage.toggle_watchlist("BBCA.JK")
        temp_storage.toggle_watchlist("BBCA.JK")
        result = temp_storage.toggle_watchlist("BBCA.JK")
        assert result is True
        items = temp_storage.get_watchlist()
        assert len(items) == 1

    def test_add_to_watchlist(self, temp_storage):
        """Add a ticker to watchlist."""
        temp_storage.add_to_watchlist("TLKM.JK", notes="Blue chip")
        items = temp_storage.get_watchlist()
        assert len(items) == 1
        assert items[0]["ticker"] == "TLKM.JK"

    def test_add_duplicate_watchlist(self, temp_storage):
        """Adding same ticker twice doesn't duplicate."""
        temp_storage.add_to_watchlist("BBCA.JK")
        temp_storage.add_to_watchlist("BBCA.JK")
        items = temp_storage.get_watchlist()
        assert len(items) == 1

    def test_remove_from_watchlist(self, temp_storage):
        """Remove from watchlist unfavorites."""
        temp_storage.add_to_watchlist("BBCA.JK")
        temp_storage.remove_from_watchlist("BBCA.JK")
        items = temp_storage.get_watchlist(favorites_only=True)
        assert len(items) == 0

    def test_get_watchlist_all(self, temp_storage):
        """Get all watchlist items including unfavorited."""
        temp_storage.add_to_watchlist("BBCA.JK")
        temp_storage.add_to_watchlist("TLKM.JK")
        temp_storage.remove_from_watchlist("BBCA.JK")
        items = temp_storage.get_watchlist(favorites_only=False)
        assert len(items) == 2

    def test_empty_watchlist(self, temp_storage):
        """Empty watchlist returns empty list."""
        items = temp_storage.get_watchlist()
        assert items == []

    def test_multiple_favorites(self, temp_storage):
        """Multiple tickers can be favorited."""
        for t in ["BBCA.JK", "TLKM.JK", "ASII.JK"]:
            temp_storage.toggle_watchlist(t)
        items = temp_storage.get_watchlist()
        assert len(items) == 3
