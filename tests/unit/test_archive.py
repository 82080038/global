"""Unit tests for ArchiveAdapter (Parquet archive on external HDD)."""


import pandas as pd

from trading_system.data.archive import ArchiveAdapter


class TestArchiveAdapter:

    def test_load_ohlcv_empty_archive(self, tmp_path):
        """Loading from empty archive should return empty DataFrame."""
        adapter = ArchiveAdapter(archive_dir=tmp_path)
        df = adapter.load_ohlcv("BBCA.JK")
        assert df.empty

    def test_save_and_load_ohlcv(self, tmp_path):
        """Save then load should return the same data."""
        adapter = ArchiveAdapter(archive_dir=tmp_path)

        test_df = pd.DataFrame({
            "tanggal": pd.date_range("2024-01-01", periods=5),
            "open": [8000, 8010, 8020, 8030, 8040],
            "high": [8050, 8060, 8070, 8080, 8090],
            "low": [7950, 7960, 7970, 7980, 7990],
            "close": [8000, 8010, 8020, 8030, 8040],
            "volume": [1e6, 2e6, 3e6, 4e6, 5e6],
        })

        adapter.save_ohlcv("TEST.JK", test_df)

        loaded = adapter.load_ohlcv("TEST.JK")
        assert not loaded.empty
        assert len(loaded) == 5
        assert "close" in loaded.columns
        assert loaded["close"].iloc[0] == 8000

    def test_load_with_date_filter(self, tmp_path):
        """Date filtering should work on archived data."""
        adapter = ArchiveAdapter(archive_dir=tmp_path)

        test_df = pd.DataFrame({
            "tanggal": pd.date_range("2024-01-01", periods=10),
            "open": [8000 + i for i in range(10)],
            "high": [8050 + i for i in range(10)],
            "low": [7950 + i for i in range(10)],
            "close": [8000 + i for i in range(10)],
            "volume": [1e6] * 10,
        })

        adapter.save_ohlcv("TEST.JK", test_df)

        loaded = adapter.load_ohlcv("TEST.JK", start="2024-01-05", end="2024-01-08")
        assert len(loaded) == 4
        assert loaded.index.min() >= pd.Timestamp("2024-01-05")
        assert loaded.index.max() <= pd.Timestamp("2024-01-08")

    def test_list_archived_tickers(self, tmp_path):
        """list_archived_tickers should return all unique tickers."""
        adapter = ArchiveAdapter(archive_dir=tmp_path)

        df1 = pd.DataFrame({"tanggal": [pd.Timestamp("2024-01-01")], "close": [8000]})
        df2 = pd.DataFrame({"tanggal": [pd.Timestamp("2024-01-01")], "close": [5000]})

        adapter.save_ohlcv("BBCA.JK", df1)
        adapter.save_ohlcv("TLKM.JK", df2)

        tickers = adapter.list_archived_tickers()
        assert "BBCA.JK" in tickers
        assert "TLKM.JK" in tickers

    def test_get_archive_info(self, tmp_path):
        """get_archive_info should return summary stats."""
        adapter = ArchiveAdapter(archive_dir=tmp_path)

        df = pd.DataFrame({
            "tanggal": [pd.Timestamp("2024-01-01")],
            "close": [8000],
            "open": [8000],
            "high": [8000],
            "low": [8000],
            "volume": [1e6],
        })
        adapter.save_ohlcv("TEST.JK", df)

        info = adapter.get_archive_info()
        assert info["ohlcv_files"] == 1
        assert info["ohlcv_size_mb"] >= 0
        assert "TEST.JK" in info["archived_tickers"]
