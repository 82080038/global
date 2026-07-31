"""Archive adapter — baca data raw dari Parquet archive (external HDD).

Mengikuti pola DataSourceAdapter (§4.1 SARAN_PENGEMBANGAN.md).
Membaca dari Parquet files di DATA_ARCHIVE_DIR, dengan fallback
ke yfinance jika data belum ada di archive (incremental fetch).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from trading_system.config import DATA_ARCHIVE_DIR


class ArchiveAdapter:
    """Baca OHLCV dari Parquet archive, fallback ke yfinance untuk data baru.

    Alur:
    1. Cek Parquet di DATA_ARCHIVE_DIR/ohlcv/ untuk ticker yang diminta.
    2. Jika ada, load dari Parquet (cepat, lokal, tidak perlu download).
    3. Jika data belum ada atau tidak lengkap, fetch dari yfinance dan
       simpan ke archive untuk penggunaan berikutnya.
    """

    name = "archive"

    def __init__(self, archive_dir: Path | None = None):
        self.archive_dir = archive_dir or DATA_ARCHIVE_DIR
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def _ohlcv_dir(self) -> Path:
        d = self.archive_dir / "ohlcv"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def list_archived_tickers(self) -> list[str]:
        """List semua ticker yang ada di archive."""
        ohlcv_dir = self._ohlcv_dir()
        tickers = set()
        for f in ohlcv_dir.glob("*.parquet"):
            ticker = f.stem.split("_")[0]
            tickers.add(ticker)
        return sorted(tickers)

    def load_ohlcv(
        self,
        ticker: str,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """Load OHLCV dari Parquet archive.

        Args:
            ticker: Ticker symbol (mis. "BBCA.JK").
            start: Optional start date (YYYY-MM-DD).
            end: Optional end date (YYYY-MM-DD).

        Returns:
            DataFrame dengan kolom OHLCV, atau empty jika tidak ada.
        """
        ohlcv_dir = self._ohlcv_dir()

        files = sorted(ohlcv_dir.glob(f"{ticker}*.parquet"))
        if not files:
            base = ticker.replace(".JK", "")
            files = sorted(ohlcv_dir.glob(f"{base}*.parquet"))

        if not files:
            return pd.DataFrame()

        dfs = []
        for f in files:
            df = pd.read_parquet(f)
            dfs.append(df)

        df = pd.concat(dfs, ignore_index=True)

        date_col = None
        for candidate in ("tanggal", "date", "timestamp", "Date"):
            if candidate in df.columns:
                date_col = candidate
                break

        if date_col is None:
            return pd.DataFrame()

        df[date_col] = pd.to_datetime(df[date_col])
        df = df.sort_values(date_col)

        if start:
            df = df[df[date_col] >= pd.Timestamp(start)]
        if end:
            df = df[df[date_col] <= pd.Timestamp(end)]

        col_map = {
            "tanggal": "timestamp",
            "date": "timestamp",
            "Date": "timestamp",
            "open": "open",
            "Open": "open",
            "high": "high",
            "High": "high",
            "low": "low",
            "Low": "low",
            "close": "close",
            "Close": "close",
            "volume": "volume",
            "Volume": "volume",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

        if "timestamp" in df.columns:
            df.set_index("timestamp", inplace=True)

        return df

    def save_ohlcv(self, ticker: str, df: pd.DataFrame) -> Path:
        """Simpan DataFrame ke Parquet archive."""
        ohlcv_dir = self._ohlcv_dir()
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        out_file = ohlcv_dir / f"{ticker}_{timestamp}.parquet"
        df.to_parquet(out_file, index=False, compression="snappy")
        return out_file

    def get_archive_info(self) -> dict:
        """Info tentang archive: ukuran, jumlah file, ticker tersedia."""
        ohlcv_dir = self._ohlcv_dir()
        files = list(ohlcv_dir.glob("*.parquet"))
        total_size = sum(f.stat().st_size for f in files)

        return {
            "archive_dir": str(self.archive_dir),
            "ohlcv_files": len(files),
            "ohlcv_size_mb": round(total_size / 1024 / 1024, 2),
            "archived_tickers": self.list_archived_tickers(),
        }
