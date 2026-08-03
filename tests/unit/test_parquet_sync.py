"""Tests for Parquet sync logic — auto-sync, raw cleanup, table sync."""

import os

import pandas as pd
import pytest

from trading_system.data.storage import DataStorage


@pytest.fixture
def storage(tmp_path, monkeypatch):
    """Storage with archive dir pointed to tmp_path."""
    monkeypatch.setenv("PARQUET_AUTO_SYNC", "1")
    monkeypatch.setattr("trading_system.config.DATA_ARCHIVE_DIR", tmp_path / "archive")
    monkeypatch.setattr("trading_system.config.RAW_ZONE", tmp_path / "raw")
    return DataStorage(db_path=tmp_path / "test_sync.db")


class TestOHLCVParquetSync:
    """Test auto-sync of OHLCV to Parquet on save_ohlcv."""

    def test_save_ohlcv_creates_parquet(self, storage, tmp_path):
        dates = pd.date_range("2024-01-01", periods=10, freq="B")
        df = pd.DataFrame({
            "ticker": "TEST.JK", "asset_class": "equity", "exchange": "IDX",
            "timestamp": dates.strftime("%Y-%m-%d"), "timeframe": "1d",
            "open": 100.0, "high": 105.0, "low": 95.0, "close": 100.0,
            "volume": 1_000_000.0, "adjusted_close": 100.0,
            "source": "test", "ingested_at": "2024-01-01", "data_quality_score": None,
        })
        storage.save_ohlcv(df)

        archive_dir = tmp_path / "archive" / "ohlcv"
        parquet_files = list(archive_dir.glob("TEST.JK_*.parquet"))
        assert len(parquet_files) >= 1

        # Verify content
        pq_df = pd.read_parquet(parquet_files[0])
        assert len(pq_df) == 10
        assert "ticker" in pq_df.columns

    def test_save_ohlcv_replaces_old_parquet(self, storage, tmp_path):
        dates = pd.date_range("2024-01-01", periods=10, freq="B")
        df1 = pd.DataFrame({
            "ticker": "TEST.JK", "asset_class": "equity", "exchange": "IDX",
            "timestamp": dates.strftime("%Y-%m-%d"), "timeframe": "1d",
            "open": 100.0, "high": 105.0, "low": 95.0, "close": 100.0,
            "volume": 1_000_000.0, "adjusted_close": 100.0,
            "source": "test", "ingested_at": "2024-01-01", "data_quality_score": None,
        })
        storage.save_ohlcv(df1)

        # Save again with more data
        dates2 = pd.date_range("2024-01-01", periods=20, freq="B")
        df2 = pd.DataFrame({
            "ticker": "TEST.JK", "asset_class": "equity", "exchange": "IDX",
            "timestamp": dates2.strftime("%Y-%m-%d"), "timeframe": "1d",
            "open": 100.0, "high": 105.0, "low": 95.0, "close": 100.0,
            "volume": 1_000_000.0, "adjusted_close": 100.0,
            "source": "test", "ingested_at": "2024-01-01", "data_quality_score": None,
        })
        storage.save_ohlcv(df2)

        archive_dir = tmp_path / "archive" / "ohlcv"
        parquet_files = list(archive_dir.glob("TEST.JK_*.parquet"))
        # Should have exactly 1 file (old one replaced)
        assert len(parquet_files) == 1
        pq_df = pd.read_parquet(parquet_files[0])
        assert len(pq_df) == 20

    def test_raw_zone_cleanup(self, storage, tmp_path):
        """Old raw zone files should be cleaned up after sync, keeping only latest."""
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        # Create old raw files manually (simulating accumulation from fetch)
        dates = pd.date_range("2024-01-01", periods=10, freq="B")
        df = pd.DataFrame({
            "ticker": "TEST.JK", "asset_class": "equity", "exchange": "IDX",
            "timestamp": dates.strftime("%Y-%m-%d"), "timeframe": "1d",
            "open": 100.0, "high": 105.0, "low": 95.0, "close": 100.0,
            "volume": 1_000_000.0, "adjusted_close": 100.0,
            "source": "test", "ingested_at": "2024-01-01", "data_quality_score": None,
        })

        # Write 3 old raw files
        for i in range(3):
            df.to_parquet(raw_dir / f"TEST.JK_1d_2024010{i}000000.parquet", index=False)

        # Now save via storage (triggers sync + cleanup)
        storage.save_ohlcv(df)

        raw_files = list(raw_dir.glob("TEST.JK_*.parquet"))
        # Should keep only 1 (the newest)
        assert len(raw_files) <= 1


class TestInstrumentMasterParquetSync:
    """Test auto-sync of instrument_master to Parquet."""

    def test_save_instrument_creates_parquet(self, storage, tmp_path):
        storage.save_instrument_master({
            "ticker": "IPO.JK",
            "ipo_date": "2025-06-01",
            "ipo_price": 1000.0,
            "status": "active",
        })

        archive_dir = tmp_path / "archive" / "instrument_master"
        parquet_files = list(archive_dir.glob("instrument_master_*.parquet"))
        assert len(parquet_files) >= 1

        pq_df = pd.read_parquet(parquet_files[0])
        assert len(pq_df) == 1
        row = pq_df.iloc[0]
        assert row["ticker"] == "IPO.JK"
        assert row["ipo_date"] == "2025-06-01"
        assert row["ipo_price"] == 1000.0


class TestTradingSuspensionsParquetSync:
    """Test auto-sync of trading_suspensions to Parquet."""

    def test_save_suspension_creates_parquet(self, storage, tmp_path):
        storage.save_suspension({
            "ticker": "SUSP.JK",
            "suspend_date": "2025-01-15",
            "resume_date": "2025-01-20",
            "reason": "price movement",
        })

        archive_dir = tmp_path / "archive" / "trading_suspensions"
        parquet_files = list(archive_dir.glob("trading_suspensions_*.parquet"))
        assert len(parquet_files) >= 1

        pq_df = pd.read_parquet(parquet_files[0])
        assert len(pq_df) == 1
        assert pq_df.iloc[0]["ticker"] == "SUSP.JK"
        assert pq_df.iloc[0]["suspend_date"] == "2025-01-15"


class TestSyncDisabled:
    """Test that sync can be disabled via env var."""

    def test_no_sync_when_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PARQUET_AUTO_SYNC", "0")
        monkeypatch.setattr("trading_system.config.DATA_ARCHIVE_DIR", tmp_path / "archive")
        monkeypatch.setattr("trading_system.config.RAW_ZONE", tmp_path / "raw")
        storage = DataStorage(db_path=tmp_path / "test_nosync.db")

        dates = pd.date_range("2024-01-01", periods=5, freq="B")
        df = pd.DataFrame({
            "ticker": "TEST.JK", "asset_class": "equity", "exchange": "IDX",
            "timestamp": dates.strftime("%Y-%m-%d"), "timeframe": "1d",
            "open": 100.0, "high": 105.0, "low": 95.0, "close": 100.0,
            "volume": 1_000_000.0, "adjusted_close": 100.0,
            "source": "test", "ingested_at": "2024-01-01", "data_quality_score": None,
        })
        storage.save_ohlcv(df)

        archive_dir = tmp_path / "archive" / "ohlcv"
        if archive_dir.exists():
            parquet_files = list(archive_dir.glob("*.parquet"))
            assert len(parquet_files) == 0


class TestSyncIpoScript:
    """Test the sync_ipo_to_instrument_master script logic."""

    def test_sync_ipo_dry_run(self, tmp_path):
        import sqlite3

        db_path = tmp_path / "test_ipo_sync.db"
        conn = sqlite3.connect(str(db_path))

        # Create tables
        conn.execute("""
            CREATE TABLE instrument_master (
                ticker TEXT PRIMARY KEY, name TEXT, sector TEXT, subsector TEXT,
                exchange TEXT, listing_date TEXT, delisting_date TEXT,
                is_active INTEGER DEFAULT 1, board TEXT, market_cap REAL,
                free_float REAL, asset_class TEXT DEFAULT 'equity', updated_at TEXT,
                ipo_date TEXT, ipo_price REAL, status TEXT DEFAULT 'active',
                lock_up_end_date TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE stock_ipo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kode TEXT, ipo_date TEXT, ipo_price REAL,
                shares_offered REAL, underwriter TEXT,
                created_at TEXT, updated_at TEXT
            )
        """)

        # Insert instrument_master records
        conn.execute("INSERT INTO instrument_master (ticker) VALUES ('BBCA.JK')")
        conn.execute("INSERT INTO instrument_master (ticker) VALUES ('TLKM.JK')")

        # Insert stock_ipo records
        conn.execute("INSERT INTO stock_ipo (kode, ipo_date, ipo_price) VALUES ('BBCA', '2020-01-01', 5000.0)")
        conn.execute("INSERT INTO stock_ipo (kode, ipo_date, ipo_price) VALUES ('UNKNOWN', '2021-01-01', 1000.0)")
        conn.commit()
        conn.close()

        from scripts.sync_ipo_to_instrument_master import sync_ipo_data
        result = sync_ipo_data(db_path, dry_run=True)

        assert result["total_legacy"] == 2
        assert result["updated"] == 1  # BBCA matched
        assert result["not_found"] == 1  # UNKNOWN not in instrument_master

        # Verify dry run didn't write
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT ipo_date FROM instrument_master WHERE ticker = 'BBCA.JK'").fetchone()
        assert row[0] is None  # not updated
        conn.close()

    def test_sync_ipo_actual(self, tmp_path):
        import sqlite3

        db_path = tmp_path / "test_ipo_sync2.db"
        conn = sqlite3.connect(str(db_path))

        conn.execute("""
            CREATE TABLE instrument_master (
                ticker TEXT PRIMARY KEY, name TEXT, sector TEXT, subsector TEXT,
                exchange TEXT, listing_date TEXT, delisting_date TEXT,
                is_active INTEGER DEFAULT 1, board TEXT, market_cap REAL,
                free_float REAL, asset_class TEXT DEFAULT 'equity', updated_at TEXT,
                ipo_date TEXT, ipo_price REAL, status TEXT DEFAULT 'active',
                lock_up_end_date TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE stock_ipo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kode TEXT, ipo_date TEXT, ipo_price REAL,
                shares_offered REAL, underwriter TEXT,
                created_at TEXT, updated_at TEXT
            )
        """)

        conn.execute("INSERT INTO instrument_master (ticker) VALUES ('BBCA.JK')")
        conn.execute("INSERT INTO stock_ipo (kode, ipo_date, ipo_price) VALUES ('BBCA', '2020-01-01', 5000.0)")
        conn.commit()
        conn.close()

        from scripts.sync_ipo_to_instrument_master import sync_ipo_data
        result = sync_ipo_data(db_path, dry_run=False)

        assert result["updated"] == 1

        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT ipo_date, ipo_price, listing_date FROM instrument_master WHERE ticker = 'BBCA.JK'").fetchone()
        assert row[0] == "2020-01-01"
        assert row[1] == 5000.0
        assert row[2] == "2020-01-01"  # listing_date also set
        conn.close()

    def test_sync_ipo_skips_existing(self, tmp_path):
        import sqlite3

        db_path = tmp_path / "test_ipo_sync3.db"
        conn = sqlite3.connect(str(db_path))

        conn.execute("""
            CREATE TABLE instrument_master (
                ticker TEXT PRIMARY KEY, name TEXT, sector TEXT, subsector TEXT,
                exchange TEXT, listing_date TEXT, delisting_date TEXT,
                is_active INTEGER DEFAULT 1, board TEXT, market_cap REAL,
                free_float REAL, asset_class TEXT DEFAULT 'equity', updated_at TEXT,
                ipo_date TEXT, ipo_price REAL, status TEXT DEFAULT 'active',
                lock_up_end_date TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE stock_ipo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kode TEXT, ipo_date TEXT, ipo_price REAL,
                shares_offered REAL, underwriter TEXT,
                created_at TEXT, updated_at TEXT
            )
        """)

        # instrument_master already has ipo_date
        conn.execute("INSERT INTO instrument_master (ticker, ipo_date) VALUES ('BBCA.JK', '2019-01-01')")
        conn.execute("INSERT INTO stock_ipo (kode, ipo_date, ipo_price) VALUES ('BBCA', '2020-01-01', 5000.0)")
        conn.commit()
        conn.close()

        from scripts.sync_ipo_to_instrument_master import sync_ipo_data
        result = sync_ipo_data(db_path, dry_run=False)

        assert result["updated"] == 0
        assert result["skipped"] == 1

        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT ipo_date FROM instrument_master WHERE ticker = 'BBCA.JK'").fetchone()
        assert row[0] == "2019-01-01"  # not overwritten
        conn.close()
