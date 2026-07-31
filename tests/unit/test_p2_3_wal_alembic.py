"""Unit tests for P2-3: WAL + executemany + Alembic schema."""

import sqlite3

from trading_system.data.storage import DataStorage


class TestWALMode:
    """Test that WAL journal mode is set persistently."""

    def test_wal_mode_enabled(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        with storage._connect() as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"

    def test_wal_persists_across_connections(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        storage1 = DataStorage(db_path=db_path)
        del storage1

        # New connection should still see WAL
        conn = sqlite3.connect(db_path)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        assert mode.lower() == "wal"


class TestExecutemanyBatch:
    """Test batch executemany for large imports."""

    def test_batch_insert(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        rows = [(f"TEST{i}.JK", f"2024-01-{i+1:02d}", 1000 + i, "test") for i in range(100)]
        sql = "INSERT OR REPLACE INTO macro_data (series_name, date, value, source) VALUES (?, ?, ?, ?)"
        n = storage.executemany_batch(sql, rows, batch_size=25)
        assert n == 100

        with storage._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM macro_data").fetchone()[0]
        assert count == 100

    def test_batch_empty(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        n = storage.executemany_batch("INSERT INTO macro_data VALUES (?, ?, ?, ?, ?)", [])
        assert n == 0

    def test_batch_large(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        rows = [(f"S{i}", "2024-01-01", float(i), "unit", "test") for i in range(12000)]
        sql = "INSERT OR REPLACE INTO macro_data (series_name, date, value, unit, source) VALUES (?, ?, ?, ?, ?)"
        n = storage.executemany_batch(sql, rows, batch_size=5000)
        assert n == 12000


class TestD1D31Tables:
    """Test that D1-D31 tables are created correctly."""

    def test_all_tables_exist(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        expected_tables = [
            "instrument_master", "fundamental_data", "macro_data",
            "foreign_flow", "broker_flow", "policy_events", "dividends",
            "sector_master", "market_calendar", "fear_greed",
            "external_events", "esg_scores", "corporate_governance",
            "stock_personality", "trade_journal", "pattern_analysis",
            "valuation_cache", "technical_indicators",
        ]
        with storage._connect() as conn:
            result = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            existing = {r[0] for r in result}

        for table in expected_tables:
            assert table in existing, f"Table {table} not found in database"

    def test_fundamental_data_insert(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        with storage._connect() as conn:
            conn.execute(
                "INSERT INTO fundamental_data (ticker, date, pe_ratio, pb_ratio, source) VALUES (?, ?, ?, ?, ?)",
                ("TEST.JK", "2024-01-01", 15.5, 2.3, "test"),
            )
            row = conn.execute("SELECT * FROM fundamental_data WHERE ticker = ?", ("TEST.JK",)).fetchone()
        assert row[0] == "TEST.JK"
        assert row[2] == 15.5

    def test_macro_data_insert(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        with storage._connect() as conn:
            conn.execute(
                "INSERT INTO macro_data (series_name, date, value, unit, source, frequency) VALUES (?, ?, ?, ?, ?, ?)",
                ("US10Y", "2024-01-01", 4.5, "%", "test", "daily"),
            )
            row = conn.execute("SELECT * FROM macro_data WHERE series_name = ?", ("US10Y",)).fetchone()
        assert row[0] == "US10Y"
        assert row[2] == 4.5

    def test_foreign_flow_insert(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        with storage._connect() as conn:
            conn.execute(
                "INSERT INTO foreign_flow (ticker, date, foreign_buy, foreign_sell, foreign_net, source) VALUES (?, ?, ?, ?, ?, ?)",
                ("TEST.JK", "2024-01-01", 1e9, 8e8, 2e8, "test"),
            )
            row = conn.execute("SELECT * FROM foreign_flow WHERE ticker = ?", ("TEST.JK",)).fetchone()
        assert row[0] == "TEST.JK"
        assert row[4] == 2e8

    def test_indexes_exist(self, tmp_path):
        storage = DataStorage(db_path=str(tmp_path / "test.db"))
        expected_indexes = [
            "idx_fundamental_ticker", "idx_fundamental_date",
            "idx_macro_series", "idx_macro_date",
            "idx_foreign_flow_ticker", "idx_foreign_flow_date",
            "idx_dividends_ticker", "idx_trade_journal_ticker",
            "idx_technical_indicators_ticker", "idx_technical_indicators_date",
        ]
        with storage._connect() as conn:
            result = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
            existing = {r[0] for r in result}
        for idx in expected_indexes:
            assert idx in existing, f"Index {idx} not found"
