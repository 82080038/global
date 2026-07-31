"""Unit tests for P2-2: DataSourceAdapter multi-source + incremental fetch."""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

from trading_system.data.acquisition import (
    CSVAdapter,
    DataSourceAdapter,
    DataSourceManager,
    SQLiteAdapter,
    normalize_ohlcv,
)


def _make_source_sqlite(tmp_path: str, n_rows=50, ticker="TEST.JK"):
    """Create a source SQLite DB with OHLCV data in legacy format."""
    db_path = str(Path(tmp_path) / "source.db")
    conn = sqlite3.connect(db_path)
    dates = pd.bdate_range("2024-01-01", periods=n_rows)
    df = pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "ticker": [ticker] * n_rows,
        "open": [1000 + i for i in range(n_rows)],
        "high": [1010 + i for i in range(n_rows)],
        "low": [990 + i for i in range(n_rows)],
        "close": [1005 + i for i in range(n_rows)],
        "adj_close": [1003 + i for i in range(n_rows)],
        "volume": [float(1e6 + i * 1000) for i in range(n_rows)],
        "data_source": ["test"] * n_rows,
    })
    df.to_sql("ohlcv", conn, if_exists="replace", index=False)
    conn.close()
    return db_path


def _make_source_csv(tmp_path: str, n_rows=50, ticker="TEST.JK"):
    """Create a source CSV with OHLCV data."""
    csv_path = str(Path(tmp_path) / "source.csv")
    dates = pd.bdate_range("2024-01-01", periods=n_rows)
    df = pd.DataFrame({
        "ticker": [ticker] * n_rows,
        "date": dates.strftime("%Y-%m-%d"),
        "open": [1000 + i for i in range(n_rows)],
        "high": [1010 + i for i in range(n_rows)],
        "low": [990 + i for i in range(n_rows)],
        "close": [1005 + i for i in range(n_rows)],
        "adj_close": [1003 + i for i in range(n_rows)],
        "volume": [float(1e6 + i * 1000) for i in range(n_rows)],
    })
    df.to_csv(csv_path, index=False)
    return csv_path


class TestSQLiteAdapter:
    """Tests for SQLiteAdapter — import from legacy SQLite DB."""

    def test_fetch(self, tmp_path):
        source_db = _make_source_sqlite(tmp_path, 50)
        adapter = SQLiteAdapter(source_db, storage=MagicMock())
        result = adapter.fetch("TEST.JK", period="max")
        assert result["status"] == "ok"
        df = result["records"]
        assert len(df) == 50
        assert "adjusted_close" in df.columns
        assert "ticker" in df.columns
        assert all(df["ticker"] == "TEST.JK")
        assert all(df["source"] == "sqlite_import")

    def test_fetch_empty(self, tmp_path):
        source_db = _make_source_sqlite(tmp_path, 50, ticker="TEST.JK")
        adapter = SQLiteAdapter(source_db, storage=MagicMock())
        result = adapter.fetch("NONEXIST.JK", period="max")
        assert result["status"] == "empty"

    def test_fetch_incremental(self, tmp_path):
        source_db = _make_source_sqlite(tmp_path, 50)
        adapter = SQLiteAdapter(source_db, storage=MagicMock())
        # Fetch all first
        result = adapter.fetch("TEST.JK", period="max")
        assert result["status"] == "ok"
        # Incremental from bar 40
        last_ts = "2024-02-26"  # ~bar 40
        result = adapter.fetch_incremental("TEST.JK", last_ts)
        assert result["status"] == "ok"
        df = result["records"]
        assert len(df) < 50  # should be less than full

    def test_fetch_incremental_no_last_ts(self, tmp_path):
        source_db = _make_source_sqlite(tmp_path, 50)
        adapter = SQLiteAdapter(source_db, storage=MagicMock())
        result = adapter.fetch_incremental("TEST.JK", None)
        assert result["status"] == "ok"
        assert len(result["records"]) == 50

    def test_normalize_columns(self, tmp_path):
        source_db = _make_source_sqlite(tmp_path, 10)
        adapter = SQLiteAdapter(source_db, storage=MagicMock())
        result = adapter.fetch("TEST.JK", period="max")
        df = result["records"]
        assert "timestamp" in df.columns
        assert "adjusted_close" in df.columns
        assert "asset_class" in df.columns
        assert "exchange" in df.columns
        assert all(df["exchange"] == "IDX")


class TestCSVAdapter:
    """Tests for CSVAdapter — import from CSV files."""

    def test_fetch(self, tmp_path):
        csv_path = _make_source_csv(tmp_path, 50)
        adapter = CSVAdapter(csv_path, storage=MagicMock())
        result = adapter.fetch("TEST.JK", period="max")
        assert result["status"] == "ok"
        df = result["records"]
        assert len(df) == 50
        assert "adjusted_close" in df.columns
        assert all(df["source"] == "csv_import")

    def test_fetch_empty(self, tmp_path):
        csv_path = _make_source_csv(tmp_path, 50, ticker="TEST.JK")
        adapter = CSVAdapter(csv_path, storage=MagicMock())
        result = adapter.fetch("NONEXIST.JK", period="max")
        assert result["status"] == "empty"

    def test_fetch_incremental(self, tmp_path):
        csv_path = _make_source_csv(tmp_path, 50)
        adapter = CSVAdapter(csv_path, storage=MagicMock())
        result = adapter.fetch_incremental("TEST.JK", "2024-02-26")
        assert result["status"] == "ok"
        df = result["records"]
        assert len(df) < 50

    def test_fetch_incremental_no_last_ts(self, tmp_path):
        csv_path = _make_source_csv(tmp_path, 50)
        adapter = CSVAdapter(csv_path, storage=MagicMock())
        result = adapter.fetch_incremental("TEST.JK", None)
        assert result["status"] == "ok"
        assert len(result["records"]) == 50

    def test_kode_column_mapping(self, tmp_path):
        csv_path = str(Path(tmp_path) / "kode_test.csv")
        df = pd.DataFrame({
            "kode": ["TEST.JK"] * 5,
            "date": pd.bdate_range("2024-01-01", periods=5).strftime("%Y-%m-%d"),
            "open": [100] * 5, "high": [110] * 5, "low": [90] * 5,
            "close": [105] * 5, "volume": [1e6] * 5,
        })
        df.to_csv(csv_path, index=False)
        adapter = CSVAdapter(csv_path, storage=MagicMock())
        result = adapter.fetch("TEST.JK", period="max")
        assert result["status"] == "ok"
        assert all(result["records"]["ticker"] == "TEST.JK")


class TestDataSourceManager:
    """Tests for DataSourceManager — multi-source routing with fallback."""

    def test_register_and_list(self, tmp_path):
        manager = DataSourceManager(storage=MagicMock())
        adapter = SQLiteAdapter("dummy.db", storage=MagicMock())
        manager.register(adapter)
        assert "sqlite_import" in manager.sources

    def test_fetch_from_specific_source(self, tmp_path):
        source_db = _make_source_sqlite(tmp_path, 30)
        manager = DataSourceManager(storage=MagicMock())
        manager.register(SQLiteAdapter(source_db, storage=MagicMock()))
        result = manager.fetch("TEST.JK", period="max", source="sqlite_import")
        assert result["status"] == "ok"
        assert len(result["records"]) == 30

    def test_fetch_fallback(self, tmp_path):
        """If first source fails, try next."""
        manager = DataSourceManager(storage=MagicMock())

        # First adapter: always fails
        failing = MagicMock(spec=DataSourceAdapter)
        failing.name = "failing"
        failing.fetch.return_value = {"status": "error", "records": pd.DataFrame(), "message": "down"}

        # Second adapter: succeeds
        source_db = _make_source_sqlite(tmp_path, 20)
        good_adapter = SQLiteAdapter(source_db, storage=MagicMock())

        manager.register(failing, priority=0)
        manager.register(good_adapter, priority=1)

        result = manager.fetch("TEST.JK", period="max")
        assert result["status"] == "ok"
        assert len(result["records"]) == 20

    def test_fetch_all_fail(self):
        manager = DataSourceManager(storage=MagicMock())
        failing = MagicMock(spec=DataSourceAdapter)
        failing.name = "failing"
        failing.fetch.return_value = {"status": "error", "records": pd.DataFrame(), "message": "down"}
        manager.register(failing)
        result = manager.fetch("TEST.JK")
        assert result["status"] == "error"
        assert "All sources failed" in result["message"]

    def test_fetch_incremental_auto_last_ts(self, tmp_path):
        """Test that fetch_incremental automatically looks up last timestamp."""
        storage = MagicMock()
        # Simulate existing data with last timestamp
        existing_df = pd.DataFrame(
            {"timestamp": ["2024-01-01", "2024-01-02", "2024-02-26"]},
            index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-02-26"]),
        )
        storage.load_ohlcv.return_value = existing_df

        source_db = _make_source_sqlite(tmp_path, 50)
        manager = DataSourceManager(storage=storage)
        manager.register(SQLiteAdapter(source_db, storage=storage))

        result = manager.fetch_incremental("TEST.JK")
        assert result["status"] == "ok"
        # Should have fewer rows than full 50
        assert len(result["records"]) < 50

    def test_fetch_incremental_no_existing_data(self, tmp_path):
        """If no existing data, incremental should fetch all."""
        storage = MagicMock()
        storage.load_ohlcv.return_value = pd.DataFrame()

        source_db = _make_source_sqlite(tmp_path, 50)
        manager = DataSourceManager(storage=storage)
        manager.register(SQLiteAdapter(source_db, storage=storage))

        result = manager.fetch_incremental("TEST.JK")
        assert result["status"] == "ok"
        assert len(result["records"]) == 50


class TestNormalizeOHLCV:
    """Tests for normalize_ohlcv function."""

    def test_adj_close_mapping(self):
        df = pd.DataFrame({
            "ticker": ["TEST.JK"],
            "timestamp": ["2024-01-01"],
            "open": [100], "high": [110], "low": [90],
            "close": [105], "volume": [1e6],
            "source": ["test"],
            "adj_close": [103],
        })
        result = normalize_ohlcv(df)
        assert "adjusted_close" in result.columns
        assert result["adjusted_close"].iloc[0] == 103

    def test_missing_adj_close_defaults_to_close(self):
        df = pd.DataFrame({
            "ticker": ["TEST.JK"],
            "timestamp": ["2024-01-01"],
            "open": [100], "high": [110], "low": [90],
            "close": [105], "volume": [1e6],
            "source": ["test"],
        })
        result = normalize_ohlcv(df)
        assert result["adjusted_close"].iloc[0] == 105
