"""Archive adapter — baca data raw dari Parquet archive (external HDD).

Mengikuti pola DataSourceAdapter (§4.1 SARAN_PENGEMBANGAN.md).
Membaca dari Parquet files di DATA_ARCHIVE_DIR, dengan fallback
ke yfinance jika data belum ada di archive (incremental fetch).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from trading_system.config import DATA_ARCHIVE_DIR, RAW_ZONE


class ArchiveAdapter:
    """Baca OHLCV dari Parquet archive, fallback ke yfinance untuk data baru.

    Alur:
    1. Cek Parquet di DATA_ARCHIVE_DIR/ohlcv/ dan RAW_ZONE/ untuk ticker.
    2. Jika ada, load dari Parquet (cepat, lokal, tidak perlu download).
    3. Jika data belum ada atau tidak lengkap, fetch dari yfinance dan
       simpan ke archive untuk penggunaan berikutnya.
    """

    name = "archive"

    def __init__(self, archive_dir: Path | None = None, raw_dir: Path | None = None):
        self.archive_dir = archive_dir or DATA_ARCHIVE_DIR
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir = raw_dir or RAW_ZONE
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def _ohlcv_dir(self) -> Path:
        d = self.archive_dir / "ohlcv"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _search_dirs(self) -> list[Path]:
        """Direktori yang dicari: archive/ohlcv/ dulu, lalu raw/."""
        return [self._ohlcv_dir(), self.raw_dir]

    def list_archived_tickers(self) -> list[str]:
        """List semua ticker yang ada di archive + raw (per-ticker + file tahunan)."""
        tickers = set()
        for search_dir in self._search_dirs():
            for f in search_dir.glob("*.parquet"):
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
        base = ticker.replace(".JK", "")
        dfs = []
        for search_dir in self._search_dirs():
            for f in sorted(search_dir.glob("ohlcv_*.parquet")):
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
        # 1. Cari file per-ticker di semua direktori (archive/ohlcv/ + raw/)
        files = []
        base = ticker.replace(".JK", "")
        for search_dir in self._search_dirs():
            files.extend(sorted(search_dir.glob(f"{ticker}*.parquet")))
            if not files:
                files.extend(sorted(search_dir.glob(f"{base}*.parquet")))
        files = sorted(set(files))

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
                # Normalize: strip timezone to avoid tz-naive vs tz-aware comparison errors
                if df["timestamp"].dt.tz is not None:
                    df["timestamp"] = df["timestamp"].dt.tz_localize(None)
            dfs[i] = df

        df = pd.concat(dfs, ignore_index=True)

        if "timestamp" not in df.columns:
            return pd.DataFrame()

        df = df.dropna(subset=["timestamp"])
        df = df.sort_values("timestamp")
        df = df.drop_duplicates(subset=["timestamp"])

        if start:
            start_ts = pd.Timestamp(start)
            if df["timestamp"].dt.tz is not None:
                start_ts = start_ts.tz_localize(df["timestamp"].dt.tz)
            df = df[df["timestamp"] >= start_ts]
        if end:
            end_ts = pd.Timestamp(end)
            if df["timestamp"].dt.tz is not None:
                end_ts = end_ts.tz_localize(df["timestamp"].dt.tz)
            df = df[df["timestamp"] <= end_ts]

        if "adj_close" in df.columns:
            df = df.rename(columns={"adj_close": "adjusted_close"})

        df.set_index("timestamp", inplace=True)
        return df

    def save_ohlcv(self, ticker: str, df: pd.DataFrame) -> Path:
        """Simpan DataFrame ke Parquet archive (permanent) dan raw zone."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        filename = f"{ticker}_{timestamp}.parquet"
        # Simpan ke archive (permanent)
        ohlcv_dir = self._ohlcv_dir()
        out_file = ohlcv_dir / filename
        df.to_parquet(out_file, index=False, compression="snappy")
        # Juga simpan ke raw zone (untuk konsistensi dengan fetch)
        raw_file = self.raw_dir / filename
        if raw_file != out_file:
            df.to_parquet(raw_file, index=False, compression="snappy")
        return out_file

    def get_archive_info(self) -> dict:
        """Info tentang archive + raw: ukuran, jumlah file, ticker tersedia."""
        all_files = []
        for search_dir in self._search_dirs():
            all_files.extend(list(search_dir.glob("*.parquet")))
        total_size = sum(f.stat().st_size for f in all_files)

        return {
            "archive_dir": str(self.archive_dir),
            "raw_dir": str(self.raw_dir),
            "ohlcv_files": len(all_files),
            "ohlcv_size_mb": round(total_size / 1024 / 1024, 2),
            "archived_tickers": self.list_archived_tickers(),
        }

    def delete_archived_ticker(self, ticker: str) -> int:
        """Delete all Parquet files for a ticker from archive + raw. Returns files deleted."""
        base = ticker.replace(".JK", "")
        count = 0
        for search_dir in self._search_dirs():
            files = list(search_dir.glob(f"{ticker}*.parquet"))
            if not files:
                files = list(search_dir.glob(f"{base}*.parquet"))
            for f in files:
                f.unlink()
                count += 1
        return count
