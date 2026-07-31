"""Unit tests for legacy data import (§13.5 #5)."""

import sqlite3
import pandas as pd
import pytest
from pathlib import Path

from trading_system.data.storage import DataStorage
from trading_system.data.import_legacy import LegacyDataImporter


def _make_source_db(tmp_path: str):
    """Create a mini saham.db for testing."""
    db_path = str(Path(tmp_path) / "source.db")
    conn = sqlite3.connect(db_path)

    # ohlcv table
    df = pd.DataFrame({
        "date": pd.bdate_range("2024-01-01", periods=10).strftime("%Y-%m-%d"),
        "ticker": ["TEST.JK"] * 10,
        "open": [100 + i for i in range(10)],
        "high": [110 + i for i in range(10)],
        "low": [90 + i for i in range(10)],
        "close": [105 + i for i in range(10)],
        "adj_close": [103 + i for i in range(10)],
        "volume": [float(1e6 + i * 1000) for i in range(10)],
        "data_source": ["test"] * 10,
    })
    df.to_sql("ohlcv", conn, if_exists="replace", index=False)

    # instruments table
    df_inst = pd.DataFrame({
        "ticker": ["TEST.JK", "BBCA.JK"],
        "name": ["Test Stock", "Bank Central Asia"],
        "instrument_type": ["equity", "equity"],
        "exchange": ["IDX", "IDX"],
        "sector": ["Technology", "Finance"],
        "industry": ["Software", "Banking"],
        "currency": ["IDR", "IDR"],
        "board": ["Main", "Main"],
        "is_active": [True, True],
    })
    df_inst.to_sql("instruments", conn, if_exists="replace", index=False)

    # macro_data table
    df_macro = pd.DataFrame({
        "date": ["2024-01-01", "2024-01-02"],
        "series_id": ["BI_RATE", "INFLATION"],
        "value": [6.0, 3.5],
        "region": ["ID", "ID"],
        "category": ["rate", "inflation"],
        "data_source": ["BI", "BPS"],
    })
    df_macro.to_sql("macro_data", conn, if_exists="replace", index=False)

    # global_market_data table
    df_global = pd.DataFrame({
        "date": pd.bdate_range("2024-01-01", periods=5).strftime("%Y-%m-%d"),
        "ticker": ["^GSPC"] * 5,
        "open": [4000 + i for i in range(5)],
        "high": [4010 + i for i in range(5)],
        "low": [3990 + i for i in range(5)],
        "close": [4005 + i for i in range(5)],
        "adj_close": [4003 + i for i in range(5)],
        "volume": [float(1e9 + i * 1e7) for i in range(5)],
        "data_source": ["yahoo"] * 5,
    })
    df_global.to_sql("global_market_data", conn, if_exists="replace", index=False)

    conn.close()
    return db_path


class TestLegacyDataImporter:
    """Tests for LegacyDataImporter."""

    def test_import_ohlcv(self, tmp_path):
        source_db = _make_source_db(tmp_path)
        target_db = str(tmp_path / "target.db")
        storage = DataStorage(db_path=target_db)
        importer = LegacyDataImporter(source_db=source_db, target_storage=storage)
        importer._import_ohlcv()

        df = storage.load_ohlcv("TEST.JK")
        assert len(df) == 10
        assert "adjusted_close" in df.columns

    def test_import_instruments(self, tmp_path):
        source_db = _make_source_db(tmp_path)
        target_db = str(tmp_path / "target.db")
        storage = DataStorage(db_path=target_db)
        importer = LegacyDataImporter(source_db=source_db, target_storage=storage)
        importer._import_instruments()

        with storage._connect() as conn:
            rows = conn.execute("SELECT * FROM instrument_master").fetchall()
        assert len(rows) == 2
        assert rows[0][0] == "TEST.JK"

    def test_import_macro_data(self, tmp_path):
        source_db = _make_source_db(tmp_path)
        target_db = str(tmp_path / "target.db")
        storage = DataStorage(db_path=target_db)
        importer = LegacyDataImporter(source_db=source_db, target_storage=storage)
        importer._import_macro_data()

        with storage._connect() as conn:
            rows = conn.execute("SELECT * FROM macro_data").fetchall()
        assert len(rows) == 2

    def test_import_global_market_data(self, tmp_path):
        source_db = _make_source_db(tmp_path)
        target_db = str(tmp_path / "target.db")
        storage = DataStorage(db_path=target_db)
        importer = LegacyDataImporter(source_db=source_db, target_storage=storage)
        importer._import_global_market_data()

        df = storage.load_ohlcv("^GSPC")
        assert len(df) == 5

    def test_import_all(self, tmp_path):
        source_db = _make_source_db(tmp_path)
        target_db = str(tmp_path / "target.db")
        storage = DataStorage(db_path=target_db)
        importer = LegacyDataImporter(source_db=source_db, target_storage=storage)
        stats = importer.import_all()

        assert stats["ohlcv"] == 10
        assert stats["instrument_master"] == 2
        assert stats["macro_data"] == 2
        assert stats["global_market_data"] == 5

    def test_import_empty_source(self, tmp_path):
        """Test import from empty source DB."""
        db_path = str(tmp_path / "empty.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE ohlcv (date TEXT, ticker TEXT, open REAL, high REAL, low REAL, close REAL, adj_close REAL, volume REAL, data_source TEXT)")
        conn.execute("CREATE TABLE instruments (ticker TEXT, name TEXT, instrument_type TEXT, exchange TEXT, sector TEXT, industry TEXT, currency TEXT, board TEXT, is_active BOOLEAN)")
        conn.execute("CREATE TABLE macro_data (date TEXT, series_id TEXT, value REAL, region TEXT, category TEXT, data_source TEXT)")
        conn.execute("CREATE TABLE global_market_data (date TEXT, ticker TEXT, open REAL, high REAL, low REAL, close REAL, adj_close REAL, volume REAL, data_source TEXT)")
        conn.close()

        target_db = str(tmp_path / "target.db")
        storage = DataStorage(db_path=target_db)
        importer = LegacyDataImporter(source_db=db_path, target_storage=storage)
        stats = importer.import_all()

        assert stats["ohlcv"] == 0
        assert stats["instrument_master"] == 0
        assert stats["macro_data"] == 0
        assert stats["global_market_data"] == 0
