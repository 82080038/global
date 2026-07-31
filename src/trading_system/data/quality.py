"""Data Quality Engine — TIP-derived quality checks for OHLCV data (CC, §4.1).

Adapted from TIP/python/ingestion/quality.py.
Uses 'timestamp' column (global convention) instead of 'time' (TIP convention).

Checks: missing bars, duplicates, zero/invalid prices, stale data, abnormal returns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pandas as pd


@dataclass
class QualityReport:
    """Data quality report for a single instrument ingestion."""
    symbol: str
    rows_checked: int = 0
    missing_bars: int = 0
    duplicates: int = 0
    zero_prices: int = 0
    invalid_prices: int = 0
    stale_data: bool = False
    abnormal_returns: int = 0
    issues: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.issues) == 0

    def summary(self) -> str:
        status = "LULUS" if self.passed else "BERMASALAH"
        return (
            f"[{status}] {self.symbol}: {self.rows_checked} bar diperiksa, "
            f"missing={self.missing_bars}, duplikat={self.duplicates}, "
            f"zero_price={self.zero_prices}, invalid={self.invalid_prices}, "
            f"stale={'ya' if self.stale_data else 'tidak'}, "
            f"abnormal_return={self.abnormal_returns}"
        )

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "rows_checked": self.rows_checked,
            "missing_bars": self.missing_bars,
            "duplicates": self.duplicates,
            "zero_prices": self.zero_prices,
            "invalid_prices": self.invalid_prices,
            "stale_data": self.stale_data,
            "abnormal_returns": self.abnormal_returns,
            "issues": self.issues,
            "passed": self.passed,
        }


def check_quality(
    df: pd.DataFrame,
    symbol: str,
    expected_freq: str = "B",
    max_stale_days: int = 7,
    abnormal_return_threshold: float = 0.25,
) -> QualityReport:
    """Run data quality checks on an OHLCV DataFrame.

    Args:
        df: OHLCV DataFrame with 'timestamp', 'open', 'high', 'low', 'close', 'volume'.
        symbol: Symbol identifier for the report.
        expected_freq: Expected frequency for gap detection ('B' = business days).
        max_stale_days: Max days allowed since last bar before flagging stale.
        abnormal_return_threshold: Absolute return threshold for flagging abnormal moves.

    Returns:
        QualityReport with findings.
    """
    report = QualityReport(symbol=symbol)

    if df is None or df.empty:
        report.issues.append("Tidak ada data")
        return report

    report.rows_checked = len(df)

    ts_col = "timestamp" if "timestamp" in df.columns else "time" if "time" in df.columns else None
    if ts_col is None:
        report.issues.append("Kolom 'timestamp' tidak ditemukan")
        return report

    df = df.sort_values(ts_col).reset_index(drop=True)

    # Check for duplicates
    dup_count = df[ts_col].duplicated().sum()
    report.duplicates = int(dup_count)
    if dup_count > 0:
        report.issues.append(f"Ditemukan {dup_count} bar duplikat")

    # Check for zero prices
    for col in ["open", "high", "low", "close"]:
        if col in df.columns:
            zero_count = (df[col] == 0).sum()
            report.zero_prices += int(zero_count)
    if report.zero_prices > 0:
        report.issues.append(f"Ditemukan {report.zero_prices} harga nol")

    # Check for invalid prices (negative)
    for col in ["open", "high", "low", "close"]:
        if col in df.columns:
            neg_count = (df[col] < 0).sum()
            report.invalid_prices += int(neg_count)
    if report.invalid_prices > 0:
        report.issues.append(f"Ditemukan {report.invalid_prices} harga negatif")

    # Check for high < low violations
    if "high" in df.columns and "low" in df.columns:
        hl_violations = (df["high"] < df["low"]).sum()
    else:
        hl_violations = 0
    if hl_violations > 0:
        report.invalid_prices += int(hl_violations)
        report.issues.append(f"Ditemukan {hl_violations} pelanggaran high < low")

    # Check for missing bars (gaps in business day frequency)
    if len(df) > 1:
        times = pd.to_datetime(df[ts_col]).dt.tz_localize(None).dt.normalize()
        expected_dates = pd.bdate_range(
            start=times.min(),
            end=times.max(),
        )
        missing = set(expected_dates) - set(times)
        report.missing_bars = len(missing)
        if report.missing_bars > 0:
            report.issues.append(f"Ditemukan {report.missing_bars} bar hilang (gap kalender bisnis)")

    # Check for stale data
    if len(df) > 0:
        last_bar = pd.to_datetime(df[ts_col].iloc[-1])
        if last_bar.tzinfo is not None:
            last_bar = last_bar.tz_localize(None)
        now = datetime.now(UTC).replace(tzinfo=None)
        days_since = (now - last_bar).days
        if days_since > max_stale_days:
            report.stale_data = True
            report.issues.append(f"Data terakhir {days_since} hari yang lalu (stale)")

    # Check for abnormal returns
    if "close" in df.columns and len(df) > 1:
        returns = df["close"].pct_change().abs()
        abnormal = (returns > abnormal_return_threshold).sum()
        report.abnormal_returns = int(abnormal)
        if abnormal > 0:
            report.issues.append(
                f"Ditemukan {abnormal} return abnormal (>{abnormal_return_threshold*100:.0f}%)"
            )

    return report
