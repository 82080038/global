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
        """List semua ticker yang ada di archive (per-ticker + file tahunan)."""
        ohlcv_dir = self._ohlcv_dir()
        tickers = set()
        for f in ohlcv_dir.glob("*.parquet"):
            stem = f.stem
            # Per-ticker file: BBCA.JK_20260801.parquet
            if "_" in stem and not stem.startswith("ohlcv_"):
                ticker = stem.split("_")[0]
                tickers.add(ticker)
            # File tahunan: ohlcv_2025.parquet — baca kolom kode
            elif stem.startswith("ohlcv_"):
                try:
                    df = pd.read_parquet(f, columns=None)
                    col = "kode" if "kode" in df.columns else "ticker"
                    for t in df[col].dropna().unique():
                        tickers.add(str(t))
                except Exception:
                    pass
        return sorted(tickers)

    def _load_yearly_files(self, ticker: str) -> list[pd.DataFrame]:
        """Baca file tahunan ohlcv_YYYY.parquet yang berisi multiple ticker."""
        ohlcv_dir = self._ohlcv_dir()
        base = ticker.replace(".JK", "")
        dfs = []
        for f in sorted(ohlcv_dir.glob("ohlcv_*.parquet")):
            try:
                df = pd.read_parquet(f)
                col = "kode" if "kode" in df.columns else "ticker"
                if col not in df.columns:
                    continue
                subset = df[df[col].astype(str) == base]
                if not subset.empty:
                    dfs.append(subset)
            except Exception:
                continue
        return dfs

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

        # 1. Cari file per-ticker: BBCA.JK_*.parquet
        files = sorted(ohlcv_dir.glob(f"{ticker}*.parquet"))
        if not files:
            base = ticker.replace(".JK", "")
            files = sorted(ohlcv_dir.glob(f"{base}*.parquet"))

        dfs = []
        for f in files:
            df = pd.read_parquet(f)
            dfs.append(df)

        # 2. Cari file tahunan: ohlcv_YYYY.parquet (multi-ticker)
        dfs.extend(self._load_yearly_files(ticker))

        if not dfs:
            return pd.DataFrame()

        # Normalisasi nama kolom tanggal sebelum concat (sumber berbeda punya
        # kolom berbeda: tanggal/date/timestamp/Date)
        for i, df in enumerate(dfs):
            for c in ("tanggal", "date", "Date"):
                if c in df.columns:
                    df = df.rename(columns={c: "timestamp"})
                    break
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
            dfs[i] = df

        df = pd.concat(dfs, ignore_index=True)

        if "timestamp" not in df.columns:
            return pd.DataFrame()

        df = df.dropna(subset=["timestamp"])
        df = df.sort_values("timestamp")
        df = df.drop_duplicates(subset=["timestamp"])

        if start:
            df = df[df["timestamp"] >= pd.Timestamp(start)]
        if end:
            df = df[df["timestamp"] <= pd.Timestamp(end)]

        if "adj_close" in df.columns:
            df = df.rename(columns={"adj_close": "adjusted_close"})

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

    def delete_archived_ticker(self, ticker: str) -> int:
        """Delete all Parquet files for a ticker from the archive. Returns files deleted."""
        ohlcv_dir = self._ohlcv_dir()
        files = list(ohlcv_dir.glob(f"{ticker}*.parquet"))
        if not files:
            base = ticker.replace(".JK", "")
            files = list(ohlcv_dir.glob(f"{base}*.parquet"))
        count = 0
        for f in files:
            f.unlink()
            count += 1
        return count
