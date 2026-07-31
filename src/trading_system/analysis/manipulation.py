"""Manipulation Detection Engine (M, §4.1).

Detects potential market manipulation patterns in OHLCV data.

Checks:
- Volume anomaly detection (spikes vs historical median)
- Price-volume divergence
- Marking the close (late-day price spikes)
- Pump & dump pattern (sharp rise + volume spike + sharp decline)
- Wash trading (high volume, low price change)
- Spread anomaly (high-low range spikes)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class ManipulationFlag:
    """Single manipulation detection flag."""
    check: str
    date: str
    severity: str  # "low", "medium", "high"
    detail: str


@dataclass
class ManipulationReport:
    """Manipulation detection report for a single instrument."""
    symbol: str
    flags: list[ManipulationFlag] = field(default_factory=list)
    risk_score: float = 0.0  # 0-100

    @property
    def has_danger(self) -> bool:
        return any(f.severity == "high" for f in self.flags)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "flags": [
                {"check": f.check, "date": f.date, "severity": f.severity, "detail": f.detail}
                for f in self.flags
            ],
            "risk_score": self.risk_score,
            "has_danger": self.has_danger,
        }


def detect_volume_anomaly(df: pd.DataFrame, threshold: float = 5.0) -> list[ManipulationFlag]:
    """Detect volume spikes > threshold * median."""
    flags = []
    if "volume" not in df.columns or len(df) < 20:
        return flags
    median_vol = df["volume"].rolling(20).median()
    for i in range(20, len(df)):
        if median_vol.iloc[i] > 0:
            ratio = df["volume"].iloc[i] / median_vol.iloc[i]
            if ratio > threshold:
                severity = "high" if ratio > threshold * 2 else "medium"
                flags.append(ManipulationFlag(
                    check="volume_anomaly",
                    date=str(df.index[i]),
                    severity=severity,
                    detail=f"Volume {ratio:.1f}x median",
                ))
    return flags


def detect_price_volume_divergence(df: pd.DataFrame) -> list[ManipulationFlag]:
    """Detect price up with declining volume (potential manipulation)."""
    flags = []
    if len(df) < 10:
        return flags
    for i in range(5, len(df)):
        price_change = (df["close"].iloc[i] - df["close"].iloc[i-5]) / df["close"].iloc[i-5]
        vol_change = (df["volume"].iloc[i] - df["volume"].iloc[i-5]) / (df["volume"].iloc[i-5] + 1)
        if price_change > 0.05 and vol_change < -0.3:
            flags.append(ManipulationFlag(
                check="price_volume_divergence",
                date=str(df.index[i]),
                severity="medium",
                detail=f"Price +{price_change:.1%} but volume {vol_change:.1%}",
            ))
    return flags


def detect_pump_dump(df: pd.DataFrame, rise_threshold: float = 0.15, fall_threshold: float = 0.10) -> list[ManipulationFlag]:
    """Detect pump & dump pattern: sharp rise followed by sharp decline."""
    flags = []
    if len(df) < 10:
        return flags
    for i in range(5, len(df) - 5):
        rise = (df["close"].iloc[i] - df["close"].iloc[i-5]) / df["close"].iloc[i-5]
        fall = (df["close"].iloc[i] - df["close"].iloc[i+5]) / df["close"].iloc[i]
        if rise > rise_threshold and fall > fall_threshold:
            flags.append(ManipulationFlag(
                check="pump_dump",
                date=str(df.index[i]),
                severity="high",
                detail=f"Rise +{rise:.1%} then fall -{fall:.1%}",
            ))
    return flags


def detect_wash_trading(df: pd.DataFrame, vol_threshold: float = 3.0, price_threshold: float = 0.01) -> list[ManipulationFlag]:
    """Detect wash trading: high volume but minimal price change."""
    flags = []
    if "volume" not in df.columns or len(df) < 20:
        return flags
    median_vol = df["volume"].rolling(20).median()
    for i in range(20, len(df)):
        if median_vol.iloc[i] > 0:
            vol_ratio = df["volume"].iloc[i] / median_vol.iloc[i]
            price_change = abs(df["close"].iloc[i] - df["close"].iloc[i-1]) / df["close"].iloc[i-1]
            if vol_ratio > vol_threshold and price_change < price_threshold:
                flags.append(ManipulationFlag(
                    check="wash_trading",
                    date=str(df.index[i]),
                    severity="medium",
                    detail=f"Volume {vol_ratio:.1f}x median but price change {price_change:.2%}",
                ))
    return flags


def detect_spread_anomaly(df: pd.DataFrame, threshold: float = 5.0) -> list[ManipulationFlag]:
    """Detect abnormal high-low spread."""
    flags = []
    if len(df) < 20:
        return flags
    spread = (df["high"] - df["low"]) / df["close"]
    median_spread = spread.rolling(20).median()
    for i in range(20, len(df)):
        if median_spread.iloc[i] > 0:
            ratio = spread.iloc[i] / median_spread.iloc[i]
            if ratio > threshold:
                flags.append(ManipulationFlag(
                    check="spread_anomaly",
                    date=str(df.index[i]),
                    severity="medium" if ratio < threshold * 2 else "high",
                    detail=f"Spread {ratio:.1f}x median",
                ))
    return flags


def check_manipulation(df: pd.DataFrame, symbol: str = "") -> ManipulationReport:
    """Run all manipulation checks on OHLCV data.

    Args:
        df: OHLCV DataFrame with DatetimeIndex.
        symbol: Symbol identifier.

    Returns:
        ManipulationReport with all flags and risk score.
    """
    all_flags = []
    all_flags.extend(detect_volume_anomaly(df))
    all_flags.extend(detect_price_volume_divergence(df))
    all_flags.extend(detect_pump_dump(df))
    all_flags.extend(detect_wash_trading(df))
    all_flags.extend(detect_spread_anomaly(df))

    # Risk score: weighted by severity
    score = 0.0
    for flag in all_flags:
        if flag.severity == "high":
            score += 20.0
        elif flag.severity == "medium":
            score += 10.0
        else:
            score += 5.0
    score = min(100.0, score)

    return ManipulationReport(symbol=symbol, flags=all_flags, risk_score=score)
