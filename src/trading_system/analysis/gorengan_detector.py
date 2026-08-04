"""Gorengan Detector — adaptasi dari pustaka/14-kendala-pasar-modal.md & 13-hal-yang-perlu-diperhatikan.md.

Deteksi saham gorengan: harga naik tajam tanpa dukungan fundamental.
Karakteristik gorengan:
- Harga naik > 50% dalam minggu (5 hari) atau > 30% dalam 10 hari
- Volume meningkat drastis (volume spike)
- Fundamental lemah (PE > 100, PE < 0, atau tidak ada data fundamental)
- Likuiditas rendah (volume harian < 1 juta lembar)

Kombinasi price spike + weak fundamental + low liquidity = gorengan.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class GorenganFlag:
    """Single gorengan detection flag."""
    flag_type: str
    severity: str  # low, medium, high, critical
    description: str
    value: float | None = None
    threshold: float | None = None


@dataclass
class GorenganReport:
    """Gorengan detection report for a single instrument."""
    symbol: str
    is_gorengan: bool = False
    risk_score: float = 0.0  # 0-100
    flags: list[GorenganFlag] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "is_gorengan": self.is_gorengan,
            "risk_score": round(self.risk_score, 2),
            "flags": [
                {
                    "flag_type": f.flag_type,
                    "severity": f.severity,
                    "description": f.description,
                    "value": f.value,
                    "threshold": f.threshold,
                }
                for f in self.flags
            ],
        }


def detect_price_spike(df: pd.DataFrame, short_window: int = 5, long_window: int = 20) -> list[GorenganFlag]:
    """Detect sharp price increase in short window."""
    flags = []
    if len(df) < long_window + short_window:
        return flags

    price_5d = (df["close"].iloc[-1] - df["close"].iloc[-short_window]) / df["close"].iloc[-short_window]
    price_10d = 0.0
    if len(df) >= 10:
        price_10d = (df["close"].iloc[-1] - df["close"].iloc[-10]) / df["close"].iloc[-10]

    if price_5d > 0.50:
        flags.append(GorenganFlag(
            flag_type="PRICE_SPIKE_5D",
            severity="critical",
            description=f"Harga naik {price_5d:.1%} dalam 5 hari. Kenaikan ekstrem tanpa fundamental.",
            value=price_5d,
            threshold=0.50,
        ))
    elif price_5d > 0.30:
        flags.append(GorenganFlag(
            flag_type="PRICE_SPIKE_5D",
            severity="high",
            description=f"Harga naik {price_5d:.1%} dalam 5 hari. Kenaikan signifikan.",
            value=price_5d,
            threshold=0.30,
        ))
    elif price_10d > 0.50:
        flags.append(GorenganFlag(
            flag_type="PRICE_SPIKE_10D",
            severity="high",
            description=f"Harga naik {price_10d:.1%} dalam 10 hari. Kenaikan tajam.",
            value=price_10d,
            threshold=0.50,
        ))
    return flags


def detect_volume_spike(df: pd.DataFrame, window: int = 20, threshold: float = 3.0) -> list[GorenganFlag]:
    """Detect volume spike relative to historical average."""
    flags = []
    if len(df) < window + 5:
        return flags

    recent_vol = df["volume"].iloc[-5:].mean()
    base_vol = df["volume"].iloc[-(window + 5):-5].mean()
    if base_vol <= 0:
        return flags
    vol_ratio = recent_vol / base_vol

    if vol_ratio > threshold:
        flags.append(GorenganFlag(
            flag_type="VOLUME_SPIKE",
            severity="high",
            description=f"Volume 5 hari terakhir {vol_ratio:.1f}x rata-rata {window} hari. "
            f"Volume mencurigakan — indikasi akumulasi terkoordinasi.",
            value=vol_ratio,
            threshold=threshold,
        ))
    elif vol_ratio > threshold * 0.67:
        flags.append(GorenganFlag(
            flag_type="VOLUME_SPIKE",
            severity="medium",
            description=f"Volume {vol_ratio:.1f}x rata-rata. Volume meningkat signifikan.",
            value=vol_ratio,
            threshold=threshold * 0.67,
        ))
    return flags


def detect_weak_fundamental(
    pe_ratio: float | None = None,
    pbv: float | None = None,
    roe: float | None = None,
    der: float | None = None,
) -> list[GorenganFlag]:
    """Detect weak or absent fundamentals."""
    flags = []

    if pe_ratio is not None:
        if pe_ratio < 0:
            flags.append(GorenganFlag(
                flag_type="NEGATIVE_PE",
                severity="high",
                description=f"PE ratio negatif ({pe_ratio:.1f}). Perusahaan rugi — harga naik tanpa earnings.",
                value=pe_ratio,
                threshold=0.0,
            ))
        elif pe_ratio > 100:
            flags.append(GorenganFlag(
                flag_type="EXTREME_PE",
                severity="high",
                description=f"PE ratio {pe_ratio:.1f} > 100. Valuasi ekstrem — tidak didukung earnings.",
                value=pe_ratio,
                threshold=100.0,
            ))
        elif pe_ratio > 50:
            flags.append(GorenganFlag(
                flag_type="HIGH_PE",
                severity="medium",
                description=f"PE ratio {pe_ratio:.1f} > 50. Valuasi sangat mahal.",
                value=pe_ratio,
                threshold=50.0,
            ))

    if roe is not None and roe < 5:
        flags.append(GorenganFlag(
            flag_type="LOW_ROE",
            severity="medium",
            description=f"ROE {roe:.1f}% < 5%. Profitabilitas lemah — kenaikan harga tidak fundamental.",
            value=roe,
            threshold=5.0,
        ))

    if der is not None and der > 3.0:
        flags.append(GorenganFlag(
            flag_type="HIGH_DER",
            severity="medium",
            description=f"D/E {der:.2f} > 3.0. Leverage tinggi — risiko keuangan besar.",
            value=der,
            threshold=3.0,
        ))

    return flags


def detect_low_liquidity(df: pd.DataFrame, min_volume: int = 1_000_000, window: int = 30) -> list[GorenganFlag]:
    """Detect low liquidity — common in gorengan stocks."""
    flags = []
    if len(df) < window:
        return flags

    avg_vol = df["volume"].iloc[-window:].mean()
    if avg_vol < min_volume:
        flags.append(GorenganFlag(
            flag_type="LOW_LIQUIDITY",
            severity="high",
            description=f"Volume rata-rata {avg_vol:,.0f} lembar/hari < {min_volume:,}. "
            f"Likuiditas rendah — harga mudah dimanipulasi.",
            value=avg_vol,
            threshold=float(min_volume),
        ))
    elif avg_vol < min_volume * 5:
        flags.append(GorenganFlag(
            flag_type="LOW_LIQUIDITY",
            severity="medium",
            description=f"Volume {avg_vol:,.0f} lembar/hari. Likuiditas terbatas.",
            value=avg_vol,
            threshold=float(min_volume * 5),
        ))
    return flags


def detect_gorengan(
    df: pd.DataFrame,
    symbol: str = "",
    pe_ratio: float | None = None,
    pbv: float | None = None,
    roe: float | None = None,
    der: float | None = None,
) -> GorenganReport:
    """Run all gorengan detection checks.

    Args:
        df: OHLCV DataFrame with DatetimeIndex.
        symbol: Stock symbol identifier.
        pe_ratio: Price-to-Earnings ratio (optional).
        pbv: Price-to-Book Value ratio (optional).
        roe: Return on Equity in percent (optional).
        der: Debt-to-Equity ratio (optional).

    Returns:
        GorenganReport with gorengan status and risk score.
    """
    all_flags: list[GorenganFlag] = []
    all_flags.extend(detect_price_spike(df))
    all_flags.extend(detect_volume_spike(df))
    all_flags.extend(detect_weak_fundamental(pe_ratio, pbv, roe, der))
    all_flags.extend(detect_low_liquidity(df))

    severity_weights = {"low": 10, "medium": 20, "high": 30, "critical": 40}
    score = sum(severity_weights.get(f.severity, 0) for f in all_flags)
    score = min(100.0, float(score))

    has_price_spike = any(f.flag_type.startswith("PRICE_SPIKE") for f in all_flags)
    has_weak_fundamental = any(f.flag_type in ("NEGATIVE_PE", "EXTREME_PE", "LOW_ROE") for f in all_flags)
    has_low_liquidity = any(f.flag_type == "LOW_LIQUIDITY" for f in all_flags)

    is_gorengan = has_price_spike and (has_weak_fundamental or has_low_liquidity)

    return GorenganReport(
        symbol=symbol,
        is_gorengan=is_gorengan,
        risk_score=score,
        flags=all_flags,
    )
