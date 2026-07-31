"""Comprehensive tests for CRUD operations — Delete methods in DataStorage and ArchiveAdapter."""

import pandas as pd

from trading_system.data.storage import DataStorage


class TestDeleteOHLCV:
    """Test delete_ohlcv CRUD operation."""

    def test_delete_existing_ticker(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        df = pd.DataFrame({
            "ticker": ["TEST.JK"] * 3,
            "timestamp": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "open": [100, 101, 102],
            "high": [105, 106, 107],
            "low": [99, 100, 101],
            "close": [103, 104, 105],
            "volume": [1000, 2000, 3000],
            "source": ["test"] * 3,
        })
        storage.save_ohlcv(df)
        deleted = storage.delete_ohlcv("TEST.JK")
        assert deleted == 3
        loaded = storage.load_ohlcv("TEST.JK")
        assert loaded.empty

    def test_delete_nonexistent_ticker(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        deleted = storage.delete_ohlcv("NONEXIST.JK")
        assert deleted == 0

    def test_delete_specific_timeframe(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        df_1d = pd.DataFrame({
            "ticker": ["TEST.JK"] * 2,
            "timestamp": ["2024-01-01", "2024-01-02"],
            "open": [100, 101], "high": [105, 106], "low": [99, 100],
            "close": [103, 104], "volume": [1000, 2000], "source": ["test"] * 2,
            "timeframe": ["1d"] * 2,
        })
        df_1h = pd.DataFrame({
            "ticker": ["TEST.JK"] * 2,
            "timestamp": ["2024-01-01 09:00", "2024-01-01 10:00"],
            "open": [100, 101], "high": [105, 106], "low": [99, 100],
            "close": [103, 104], "volume": [1000, 2000], "source": ["test"] * 2,
            "timeframe": ["1h"] * 2,
        })
        storage.save_ohlcv(df_1d)
        storage.save_ohlcv(df_1h)
        deleted = storage.delete_ohlcv("TEST.JK", timeframe="1d")
        assert deleted == 2
        remaining_1h = storage.load_ohlcv("TEST.JK", timeframe="1h")
        assert len(remaining_1h) == 2


class TestDeleteScores:
    """Test delete_scores CRUD operation."""

    def test_delete_by_ticker(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        storage.save_score("TEST.JK", "technical", 75.0, {"rsi": 70})
        storage.save_score("OTHER.JK", "technical", 80.0, {"rsi": 65})
        deleted = storage.delete_scores(ticker="TEST.JK")
        assert deleted == 1
        scores = storage.load_scores(ticker="OTHER.JK")
        assert len(scores) == 1

    def test_delete_by_engine(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        storage.save_score("TEST.JK", "technical", 75.0, {})
        storage.save_score("TEST.JK", "fundamental", 80.0, {})
        deleted = storage.delete_scores(ticker="TEST.JK", engine="technical")
        assert deleted == 1
        scores = storage.load_scores(ticker="TEST.JK")
        assert len(scores) == 1
        assert scores.iloc[0]["engine"] == "fundamental"


class TestDeleteOrders:
    """Test delete_orders CRUD operation."""

    def test_delete_all(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        storage.save_order("TEST.JK", "BUY", 100, 5000)
        storage.save_order("TEST.JK", "SELL", 100, 5100)
        deleted = storage.delete_orders()
        assert deleted == 2
        assert storage.get_orders() == []

    def test_delete_by_ticker(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        storage.save_order("TEST.JK", "BUY", 100, 5000)
        storage.save_order("OTHER.JK", "BUY", 200, 3000)
        deleted = storage.delete_orders(ticker="TEST.JK")
        assert deleted == 1
        orders = storage.get_orders()
        assert len(orders) == 1
        assert orders[0]["ticker"] == "OTHER.JK"


class TestAuditLogCRUD:
    """Test get_audit_logs and delete_audit_logs."""

    def test_get_audit_logs(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        storage.audit("test.event", {"key": "value"})
        storage.audit("other.event", {"key": "value2"})
        logs = storage.get_audit_logs()
        assert len(logs) == 2

    def test_get_audit_logs_filtered(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        storage.audit("decision.buy", {"ticker": "TEST.JK"})
        storage.audit("decision.sell", {"ticker": "TEST.JK"})
        storage.audit("order.placed", {"ticker": "TEST.JK"})
        logs = storage.get_audit_logs(event_type="decision")
        assert len(logs) == 2

    def test_delete_audit_logs_by_event_type(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        storage.audit("decision.buy", {"ticker": "TEST.JK"})
        storage.audit("order.placed", {"ticker": "TEST.JK"})
        deleted = storage.delete_audit_logs(event_type="decision")
        assert deleted == 1
        logs = storage.get_audit_logs()
        assert len(logs) == 1
        assert logs[0]["event_type"] == "order.placed"


class TestDeletePosition:
    """Test delete_position CRUD operation."""

    def test_delete_existing(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        pos_id = storage.save_position("TEST.JK", 100, 5000)
        deleted = storage.delete_position(pos_id)
        assert deleted is True
        assert storage.get_open_position("TEST.JK") is None

    def test_delete_nonexistent(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        deleted = storage.delete_position(9999)
        assert deleted is False


class TestDeleteAIWeights:
    """Test delete_ai_weights CRUD operation."""

    def test_delete_by_ticker(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        storage.save_ai_weights({"technical": 0.5}, ticker="TEST.JK")
        storage.save_ai_weights({"technical": 0.3}, ticker="OTHER.JK")
        deleted = storage.delete_ai_weights(ticker="TEST.JK")
        assert deleted == 1
        weights = storage.get_ai_weights(ticker="OTHER.JK", max_age_days=365)
        assert weights is not None


class TestDeleteEquitySnapshots:
    """Test delete_equity_snapshots CRUD operation."""

    def test_delete_all(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        storage.save_equity_snapshot(equity=100000)
        deleted = storage.delete_equity_snapshots()
        assert deleted >= 1
        assert storage.get_equity_snapshots() == []


class TestDeleteDailyRiskMetrics:
    """Test delete_daily_risk_metrics CRUD operation."""

    def test_delete_all(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        storage.save_daily_risk_metrics(1.0, 2.0, 1.5, 2.5, 0.1, 0.15)
        deleted = storage.delete_daily_risk_metrics()
        assert deleted >= 1
        assert storage.get_daily_risk_metrics() == []


class TestDeleteRelationships:
    """Test delete_relationships CRUD operation."""

    def test_delete_by_asset(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        storage.save_relationship("A", "B", 30, 0.8, 0)
        storage.save_relationship("C", "D", 30, 0.6, 1)
        deleted = storage.delete_relationships(asset_a="A")
        assert deleted == 1
        rels = storage.load_relationships()
        assert len(rels) == 1


class TestDeleteCorporateActions:
    """Test delete_corporate_actions CRUD operation."""

    def test_delete_by_ticker(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        storage.save_corporate_action({
            "ticker": "TEST.JK", "action_type": "dividend",
            "ex_date": "2024-01-01", "value": 100, "unit": "IDR", "source": "test",
        })
        deleted = storage.delete_corporate_actions("TEST.JK")
        assert deleted == 1
        actions = storage.load_corporate_actions("TEST.JK")
        assert actions.empty


class TestDeleteNews:
    """Test delete_news CRUD operation."""

    def test_delete_all(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        with storage._connect() as conn:
            conn.execute(
                "INSERT INTO news (news_id, headline, published_at, source) VALUES (?, ?, ?, ?)",
                ("n1", "Test news", "2024-01-01", "test"),
            )
        deleted = storage.delete_news()
        assert deleted == 1


class TestArchiveDelete:
    """Test ArchiveAdapter.delete_archived_ticker."""

    def test_delete_archived_files(self, tmp_path):
        from trading_system.data.archive import ArchiveAdapter
        adapter = ArchiveAdapter(archive_dir=tmp_path / "archive")
        df = pd.DataFrame({
            "date": ["2024-01-01", "2024-01-02"],
            "open": [100, 101], "high": [105, 106], "low": [99, 100],
            "close": [103, 104], "volume": [1000, 2000],
        })
        adapter.save_ohlcv("TEST.JK", df)
        adapter.save_ohlcv("OTHER.JK", df)
        deleted = adapter.delete_archived_ticker("TEST.JK")
        assert deleted == 1
        tickers = adapter.list_archived_tickers()
        assert "TEST.JK" not in tickers
        assert "OTHER.JK" in tickers

    def test_delete_nonexistent(self, tmp_path):
        from trading_system.data.archive import ArchiveAdapter
        adapter = ArchiveAdapter(archive_dir=tmp_path / "archive")
        deleted = adapter.delete_archived_ticker("NONEXIST.JK")
        assert deleted == 0
