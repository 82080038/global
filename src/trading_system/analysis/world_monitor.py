"""World Monitor Intelligence — 7-signal market composite + CII scoring.

Component W — reverse-engineered from worldmonitor (TypeScript) and re-implemented in Python.

Two key concepts adopted:
1. **7-signal market composite** — detects cross-source patterns (convergence, velocity,
   divergence, sector cascade) from news + market data streams.
2. **Country Instability Index (CII)** — 4-component geopolitical risk score:
   U (Unrest), C (Conflict), S (Security), I (Information), blended with baseline risk
   and event multipliers per country.

Reference: https://github.com/82080038/worldmonitor — docs/methodology/cii-risk-scores.mdx
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np

# ====================== CII Country Weights ======================

CII_COUNTRY_WEIGHTS: dict[str, dict[str, float]] = {
    "US": {"baseline_risk": 5, "event_multiplier": 0.3},
    "RU": {"baseline_risk": 35, "event_multiplier": 2.0},
    "CN": {"baseline_risk": 25, "event_multiplier": 2.5},
    "UA": {"baseline_risk": 50, "event_multiplier": 0.8},
    "IR": {"baseline_risk": 40, "event_multiplier": 2.0},
    "IL": {"baseline_risk": 45, "event_multiplier": 0.7},
    "TW": {"baseline_risk": 30, "event_multiplier": 1.5},
    "KP": {"baseline_risk": 45, "event_multiplier": 3.0},
    "SA": {"baseline_risk": 20, "event_multiplier": 2.0},
    "TR": {"baseline_risk": 25, "event_multiplier": 1.2},
    "ID": {"baseline_risk": 15, "event_multiplier": 0.8},
    "JP": {"baseline_risk": 5, "event_multiplier": 0.5},
    "KR": {"baseline_risk": 15, "event_multiplier": 0.8},
    "IN": {"baseline_risk": 20, "event_multiplier": 0.8},
    "BR": {"baseline_risk": 15, "event_multiplier": 0.6},
    "MX": {"baseline_risk": 35, "event_multiplier": 1.0},
    "DE": {"baseline_risk": 5, "event_multiplier": 0.5},
    "GB": {"baseline_risk": 5, "event_multiplier": 0.5},
    "FR": {"baseline_risk": 10, "event_multiplier": 0.6},
    "AU": {"baseline_risk": 5, "event_multiplier": 0.4},
}

DEFAULT_BASELINE_RISK = 15.0
DEFAULT_EVENT_MULTIPLIER = 1.0


def get_country_weight(country_code: str) -> dict[str, float]:
    """Get CII baseline risk and event multiplier for a country."""
    return CII_COUNTRY_WEIGHTS.get(
        country_code.upper(),
        {"baseline_risk": DEFAULT_BASELINE_RISK, "event_multiplier": DEFAULT_EVENT_MULTIPLIER},
    )


# ====================== CII Scoring ======================

@dataclass
class CIIComponents:
    """Four CII sub-scores (0-100 each)."""
    unrest: float = 0.0        # U — civil disorder, protests, outages
    conflict: float = 0.0     # C — kinetic activity, battles, strikes
    security: float = 0.0     # S — military tempo, GPS jamming
    information: float = 0.0  # I — news headline pressure


@dataclass
class CIIScore:
    """Full CII score for a country."""
    country_code: str
    components: CIIComponents
    event_score: float
    combined_score: float
    trend: str = "stable"  # rising, falling, stable
    timestamp: str = ""
    methodology_version: str = "v1-python"


def compute_cii_score(
    country_code: str,
    unrest: float = 0,
    conflict: float = 0,
    security: float = 0,
    information: float = 0,
    boosts: dict[str, float] | None = None,
) -> CIIScore:
    """Compute CII combined score for a country.

    Formula (from worldmonitor methodology):
        eventScore = U*0.25 + C*0.30 + S*0.20 + I*0.25
        composite  = baseline*0.4 + eventScore*0.6 + sum(boosts)

    Each component is 0-100. Boosts are optional additions with caps.
    """
    weights = get_country_weight(country_code)
    baseline = weights["baseline_risk"]
    multiplier = weights["event_multiplier"]

    components = CIIComponents(
        unrest=min(100, unrest * multiplier),
        conflict=min(100, conflict * multiplier),
        security=min(100, security * multiplier),
        information=min(100, information),
    )

    event_score = (
        components.unrest * 0.25
        + components.conflict * 0.30
        + components.security * 0.20
        + components.information * 0.25
    )

    combined = baseline * 0.4 + event_score * 0.6

    boosts = boosts or {}
    boost_caps = {
        "climate": 15, "cyber": 12, "fire": 8, "advisory": 15,
        "displacement": 20, "news_urgency": 5, "earthquake": 25,
        "sanctions": 14, "ais": 10,
    }
    for key, value in boosts.items():
        cap = boost_caps.get(key, 0)
        combined += min(cap, value)

    combined = max(0, min(100, combined))

    return CIIScore(
        country_code=country_code.upper(),
        components=components,
        event_score=float(event_score),
        combined_score=float(combined),
        timestamp=datetime.now(UTC).isoformat(),
    )


# ====================== 7-Signal Market Composite ======================

SIGNAL_TYPES = [
    "convergence",       # 3+ source types report same story within 30 min
    "triangulation",     # Wire + Government + Intel sources align
    "velocity_spike",    # Topic mention rate doubles with 6+ sources/hour
    "keyword_spike",     # Term frequency rises significantly above baseline
    "prediction_leading",  # Prediction market moves 5%+ with low news
    "news_leads_markets",  # High news velocity without market move
    "silent_divergence",   # Market moves 2%+ with no correlated news
    "market_move_explained",  # Market moves 2%+ with correlated news
    "sector_cascade",    # Multiple related sectors moving same direction
]


@dataclass
class MarketSignal:
    """A single market intelligence signal."""
    signal_type: str
    severity: str  # low, medium, high
    title: str
    description: str
    confidence: float
    timestamp: str = ""
    affected_assets: list[str] = field(default_factory=list)


def detect_convergence(
    news_items: list[dict],
    window_minutes: int = 30,
    min_sources: int = 3,
) -> list[MarketSignal]:
    """Detect convergence — multiple source types reporting same story within window."""
    if len(news_items) < min_sources:
        return []

    from datetime import datetime as dt
    from datetime import timedelta

    signals = []
    parsed = []
    for item in news_items:
        ts_str = item.get("timestamp", "")
        try:
            ts = dt.fromisoformat(ts_str.replace("Z", "+00:00"))
        except Exception:
            continue
        parsed.append((ts, item))

    parsed.sort(key=lambda x: x[0])

    for i in range(len(parsed)):
        window_end = parsed[i][0] + timedelta(minutes=window_minutes)
        window_items = [parsed[j][1] for j in range(len(parsed)) if parsed[i][0] <= parsed[j][0] <= window_end]
        source_types = set(item.get("source_type", "unknown") for item in window_items)
        if len(source_types) >= min_sources:
            signals.append(MarketSignal(
                signal_type="convergence",
                severity="high",
                title=f"Convergence: {len(source_types)} source types aligning",
                description=f"Multiple independent channels confirming same event within {window_minutes}min",
                confidence=min(1.0, len(source_types) / 5),
                timestamp=datetime.now(UTC).isoformat(),
            ))
            break  # One convergence signal per batch
    return signals


def detect_velocity_spike(
    mention_counts: list[int],
    baseline: float | None = None,
) -> list[MarketSignal]:
    """Detect velocity spike — topic mention rate doubles with 6+ sources/hour."""
    if len(mention_counts) < 2:
        return []

    if baseline is None:
        baseline = float(np.mean(mention_counts[:-1])) if len(mention_counts) > 1 else 0

    signals = []
    for i in range(1, len(mention_counts)):
        current = mention_counts[i]
        if baseline > 0 and current >= baseline * 2 and current >= 6:
            signals.append(MarketSignal(
                signal_type="velocity_spike",
                severity="high" if current >= baseline * 3 else "medium",
                title=f"Velocity spike: {current} mentions/hour (baseline {baseline:.0f})",
                description="Story accelerating rapidly across news ecosystem",
                confidence=min(1.0, current / (baseline * 4)),
                timestamp=datetime.now(UTC).isoformat(),
            ))
    return signals


def detect_silent_divergence(
    market_moves: list[dict],
    news_count: int = 0,
    threshold_pct: float = 2.0,
) -> list[MarketSignal]:
    """Detect silent divergence — market moves 2%+ with no correlated news."""
    signals = []
    for move in market_moves:
        pct = abs(move.get("change_pct", 0))
        if pct >= threshold_pct and news_count == 0:
            signals.append(MarketSignal(
                signal_type="silent_divergence",
                severity="high" if pct >= 5 else "medium",
                title=f"Silent divergence: {move.get('ticker', '?')} moved {pct:.1f}% with no news",
                description="Unexplained price action — possible insider knowledge or algorithm-driven",
                confidence=min(1.0, pct / 10),
                affected_assets=[move.get("ticker", "")],
                timestamp=datetime.now(UTC).isoformat(),
            ))
    return signals


def detect_sector_cascade(
    sector_moves: dict[str, float],
    threshold_pct: float = 1.5,
    min_sectors: int = 3,
) -> list[MarketSignal]:
    """Detect sector cascade — multiple related sectors moving same direction."""
    up_sectors = [s for s, pct in sector_moves.items() if pct >= threshold_pct]
    down_sectors = [s for s, pct in sector_moves.items() if pct <= -threshold_pct]

    signals = []
    if len(up_sectors) >= min_sectors:
        signals.append(MarketSignal(
            signal_type="sector_cascade",
            severity="high" if len(up_sectors) >= 5 else "medium",
            title=f"Sector cascade UP: {', '.join(up_sectors[:5])}",
            description=f"{len(up_sectors)} sectors moving up >{threshold_pct}%",
            confidence=min(1.0, len(up_sectors) / 8),
            affected_assets=up_sectors,
            timestamp=datetime.now(UTC).isoformat(),
        ))
    if len(down_sectors) >= min_sectors:
        signals.append(MarketSignal(
            signal_type="sector_cascade",
            severity="high" if len(down_sectors) >= 5 else "medium",
            title=f"Sector cascade DOWN: {', '.join(down_sectors[:5])}",
            description=f"{len(down_sectors)} sectors moving down >{threshold_pct}%",
            confidence=min(1.0, len(down_sectors) / 8),
            affected_assets=down_sectors,
            timestamp=datetime.now(UTC).isoformat(),
        ))
    return signals


def compute_market_composite(
    news_items: list[dict] | None = None,
    mention_counts: list[int] | None = None,
    market_moves: list[dict] | None = None,
    sector_moves: dict[str, float] | None = None,
    news_count: int = 0,
) -> dict[str, Any]:
    """Compute 7-signal market composite from available data streams.

    Returns summary with all detected signals and a composite risk score.
    """
    all_signals: list[MarketSignal] = []

    if news_items:
        all_signals.extend(detect_convergence(news_items))
    if mention_counts:
        all_signals.extend(detect_velocity_spike(mention_counts))
    if market_moves is not None:
        all_signals.extend(detect_silent_divergence(market_moves, news_count))
    if sector_moves:
        all_signals.extend(detect_sector_cascade(sector_moves))

    by_type: dict[str, int] = {}
    for s in all_signals:
        by_type[s.signal_type] = by_type.get(s.signal_type, 0) + 1

    high_severity = len([s for s in all_signals if s.severity == "high"])
    composite_score = min(100, len(all_signals) * 10 + high_severity * 15)

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "total_signals": len(all_signals),
        "by_type": by_type,
        "high_severity_count": high_severity,
        "composite_score": float(composite_score),
        "signals": [
            {
                "signal_type": s.signal_type,
                "severity": s.severity,
                "title": s.title,
                "description": s.description,
                "confidence": s.confidence,
                "affected_assets": s.affected_assets,
            }
            for s in all_signals
        ],
    }
