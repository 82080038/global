"""Behavioral Risk Score — adaptasi dari pustaka/09-behavioral-finance.md & 13-hal-yang-perlu-diperhatikan.md.

Mendeteksi bias kognitif dan emosional dari pola price/volume:
- FOMO / Herding: harga naik tajam + volume spike (chasing momentum)
- Loss aversion / Disposition effect: harga di bawah MA lama, volume turun (holders tidak mau cut loss)
- Overconfidence: turnover tinggi (volume/market cap ratio elevated)
- Recency bias: return jangka pendek disproportionately positive vs jangka panjang
- Anchoring: harga oscillate di sekitar level tertentu tanpa breakout
- Mental accounting: profit-taking pattern (sell winners too early, hold losers)

Output: behavioral risk score 0-100 dan list of detected biases.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class BehavioralBias:
    """Single detected behavioral bias."""
    bias_type: str
    severity: str  # low, medium, high
    description: str
    value: float | None = None
    threshold: float | None = None


@dataclass
class BehavioralRiskReport:
    """Behavioral risk assessment report."""
    score: float = 0.0  # 0-100, higher = more behavioral risk
    biases: list[BehavioralBias] = field(default_factory=list)

    @property
    def has_high_risk(self) -> bool:
        return any(b.severity == "high" for b in self.biases)

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 2),
            "has_high_risk": self.has_high_risk,
            "biases": [
                {
                    "bias_type": b.bias_type,
                    "severity": b.severity,
                    "description": b.description,
                    "value": b.value,
                    "threshold": b.threshold,
                }
                for b in self.biases
            ],
        }


def detect_fomo_herding(df: pd.DataFrame, window: int = 10) -> list[BehavioralBias]:
    """Detect FOMO/herding: sharp price rise + volume spike in short window."""
    biases = []
    if len(df) < window + 5:
        return biases

    recent = df.iloc[-window:]
    price_change = (recent["close"].iloc[-1] - recent["close"].iloc[0]) / recent["close"].iloc[0]
    avg_vol_recent = recent["volume"].mean()
    avg_vol_base = df["volume"].rolling(20).mean().iloc[-(window + 5)]
    if pd.isna(avg_vol_base) or avg_vol_base <= 0:
        return biases
    vol_ratio = avg_vol_recent / avg_vol_base

    if price_change > 0.15 and vol_ratio > 2.0:
        biases.append(BehavioralBias(
            bias_type="FOMO_HERDING",
            severity="high",
            description=f"Harga naik {price_change:.1%} dalam {window} hari dengan volume {vol_ratio:.1f}x rata-rata. "
            f"Indikasi FOMO/herding — investor mengejar momentum.",
            value=price_change,
            threshold=0.15,
        ))
    elif price_change > 0.10 and vol_ratio > 1.5:
        biases.append(BehavioralBias(
            bias_type="FOMO_HERDING",
            severity="medium",
            description=f"Harga naik {price_change:.1%} dengan volume {vol_ratio:.1f}x. "
            f"Momentum chasing mulai terlihat.",
            value=price_change,
            threshold=0.10,
        ))
    return biases


def detect_loss_aversion(df: pd.DataFrame, ma_period: int = 50, window: int = 30) -> list[BehavioralBias]:
    """Detect loss aversion: price below MA for extended period with declining volume."""
    biases = []
    if len(df) < ma_period + window:
        return biases

    ma = df["close"].rolling(ma_period).mean()
    recent_ma = ma.iloc[-window:]
    below_ma_count = (df["close"].iloc[-window:] < recent_ma).sum()
    below_ma_ratio = below_ma_count / window

    vol_recent = df["volume"].iloc[-window:].mean()
    vol_base = df["volume"].iloc[-(window * 2):-window].mean()
    vol_decline = (vol_base - vol_recent) / vol_base if vol_base > 0 else 0

    if below_ma_ratio > 0.8 and vol_decline > 0.3:
        biases.append(BehavioralBias(
            bias_type="LOSS_AVERSION",
            severity="high",
            description=f"Harga di bawah MA{ma_period} selama {below_ma_ratio:.0%} dari {window} hari terakhir, "
            f"volume turun {vol_decline:.0%}. Indikasi loss aversion — holders tidak mau cut loss.",
            value=below_ma_ratio,
            threshold=0.8,
        ))
    elif below_ma_ratio > 0.6 and vol_decline > 0.15:
        biases.append(BehavioralBias(
            bias_type="LOSS_AVERSION",
            severity="medium",
            description=f"Harga di bawah MA{ma_period} selama {below_ma_ratio:.0%}, volume turun {vol_decline:.0%}. "
            f"Tendensi menahan posisi rugi.",
            value=below_ma_ratio,
            threshold=0.6,
        ))
    return biases


def detect_overconfidence(df: pd.DataFrame, window: int = 20) -> list[BehavioralBias]:
    """Detect overconfidence: high turnover (volume relative to recent average)."""
    biases = []
    if len(df) < window * 3:
        return biases

    vol_recent = df["volume"].iloc[-window:].mean()
    vol_long = df["volume"].iloc[-(window * 3):-window].mean()
    if vol_long <= 0:
        return biases
    turnover_ratio = vol_recent / vol_long

    if turnover_ratio > 3.0:
        biases.append(BehavioralBias(
            bias_type="OVERCONFIDENCE",
            severity="high",
            description=f"Volume perdagangan {turnover_ratio:.1f}x rata-rata jangka panjang. "
            f"Overtrading — indikasi overconfidence.",
            value=turnover_ratio,
            threshold=3.0,
        ))
    elif turnover_ratio > 2.0:
        biases.append(BehavioralBias(
            bias_type="OVERCONFIDENCE",
            severity="medium",
            description=f"Volume {turnover_ratio:.1f}x normal. Aktivitas trading meningkat signifikan.",
            value=turnover_ratio,
            threshold=2.0,
        ))
    return biases


def detect_recency_bias(df: pd.DataFrame, short_window: int = 5, long_window: int = 60) -> list[BehavioralBias]:
    """Detect recency bias: short-term returns disproportionately positive vs long-term."""
    biases = []
    if len(df) < long_window + short_window:
        return biases

    short_return = (df["close"].iloc[-1] - df["close"].iloc[-short_window]) / df["close"].iloc[-short_window]
    long_return = (df["close"].iloc[-1] - df["close"].iloc[-long_window]) / df["close"].iloc[-long_window]

    if short_return > 0.10 and long_return < -0.05:
        biases.append(BehavioralBias(
            bias_type="RECENCY_BIAS",
            severity="high",
            description=f"Return {short_window} hari: +{short_return:.1%}, return {long_window} hari: {long_return:.1%}. "
            f"Overweight performa terbaru — jangka panjang masih negatif.",
            value=short_return,
            threshold=0.10,
        ))
    elif short_return > 0.05 and long_return < 0:
        biases.append(BehavioralBias(
            bias_type="RECENCY_BIAS",
            severity="medium",
            description=f"Return jangka pendek positif (+{short_return:.1%}) tapi jangka panjang negatif ({long_return:.1%}). "
            f"Recency bias mulai terbentuk.",
            value=short_return,
            threshold=0.05,
        ))
    return biases


def detect_anchoring(df: pd.DataFrame, window: int = 30, tolerance: float = 0.05) -> list[BehavioralBias]:
    """Detect anchoring: price oscillating around a level without breakout."""
    biases = []
    if len(df) < window:
        return biases

    recent = df["close"].iloc[-window:]
    mean_price = recent.mean()
    if mean_price <= 0:
        return biases
    deviations = (recent - mean_price) / mean_price
    max_dev = deviations.abs().max()
    within_band = (deviations.abs() <= tolerance).sum()
    within_ratio = within_band / window

    if within_ratio > 0.8 and max_dev < tolerance * 1.5:
        biases.append(BehavioralBias(
            bias_type="ANCHORING",
            severity="medium",
            description=f"Harga terjebak dalam band {tolerance:.0%} dari Rp{mean_price:,.0f} selama {window} hari. "
            f"Indikasi anchoring — market menunggu katalis untuk breakout.",
            value=within_ratio,
            threshold=0.8,
        ))
    return biases


def detect_disposition_effect(df: pd.DataFrame, window: int = 20) -> list[BehavioralBias]:
    """Detect disposition effect: selling winners too early (volume spike on small gain) while holding losers."""
    biases = []
    if len(df) < window + 10:
        return biases

    recent = df.iloc[-window:]
    gains = recent["close"].pct_change()
    small_gains = (gains > 0.02) & (gains < 0.05)
    vol_on_small_gains = recent.loc[small_gains, "volume"].mean() if small_gains.any() else 0
    vol_overall = recent["volume"].mean()
    if vol_overall <= 0:
        return biases
    vol_ratio = vol_on_small_gains / vol_overall

    losses = gains < -0.02
    vol_on_losses = recent.loc[losses, "volume"].mean() if losses.any() else 0
    vol_loss_ratio = vol_on_losses / vol_overall if vol_overall > 0 else 0

    if vol_ratio > 1.5 and vol_loss_ratio < 0.8:
        biases.append(BehavioralBias(
            bias_type="DISPOSITION_EFFECT",
            severity="medium",
            description=f"Volume tinggi pada gain kecil ({vol_ratio:.1f}x normal) tapi rendah pada loss ({vol_loss_ratio:.1f}x). "
            f"Menjual pemenang terlalu cepat, menahan pecundang.",
            value=vol_ratio,
            threshold=1.5,
        ))
    return biases


def assess_behavioral_risk(df: pd.DataFrame) -> BehavioralRiskReport:
    """Run all behavioral bias detection checks on OHLCV data.

    Args:
        df: OHLCV DataFrame with DatetimeIndex.

    Returns:
        BehavioralRiskReport with aggregate score and detected biases.
    """
    all_biases: list[BehavioralBias] = []
    all_biases.extend(detect_fomo_herding(df))
    all_biases.extend(detect_loss_aversion(df))
    all_biases.extend(detect_overconfidence(df))
    all_biases.extend(detect_recency_bias(df))
    all_biases.extend(detect_anchoring(df))
    all_biases.extend(detect_disposition_effect(df))

    severity_weights = {"low": 10, "medium": 20, "high": 35}
    score = sum(severity_weights.get(b.severity, 0) for b in all_biases)
    score = min(100.0, float(score))

    return BehavioralRiskReport(score=score, biases=all_biases)
