"""No-Trade Engine (Z, §4.1).

Raw copy from TIP/python/engines/no_trade.py.
Determines when to override alpha signals with NO_TRADE.

Gates:
- Data quality failure
- Low confidence
- Low liquidity
- Event risk (earnings, corporate action proximity)
- Model disagreement
- Regime uncertainty
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

NOTRADE_VERSION = "1.1"


@dataclass
class NoTradeConfig:
    min_confidence: float = 0.2
    min_composite_alpha: float = 0.3
    min_liquidity_volume: int = 100_000
    min_bars_history: int = 60
    max_stale_days: int = 7
    event_risk_window_days: int = 5
    regime_blocklist: list = field(default_factory=lambda: ["crisis", "unknown"])
    min_model_agreement: float = 0.6
    ipo_lockup_days: int = 0  # 0 = use lock_up_end_date from instrument_master; >0 = override
    ipo_min_history_days: int = 20  # min bars of post-IPO history before trading


@dataclass
class NoTradeResult:
    instrument_id: int
    symbol: str
    decision: str  # "NO_TRADE" or "PROCEED"
    gates_failed: list[str]
    gates_passed: list[str]
    reason_codes: list[str]


class NoTradeEngine:
    """Evaluate No-Trade gates for each instrument.

    Any gate failure results in NO_TRADE decision.
    """

    def __init__(
        self,
        config: NoTradeConfig | None = None,
        notrade_version: str = NOTRADE_VERSION,
    ):
        self.config = config or NoTradeConfig()
        self.notrade_version = notrade_version

    def evaluate(
        self,
        alpha_signal: dict[str, Any],
        regime_state: str,
        data_quality: dict[str, Any] | None = None,
        liquidity_volume: int | None = None,
        bars_history: int | None = None,
        latest_data_date: datetime | None = None,
        event_risk: bool = False,
        model_agreement: float = 1.0,
        instrument_status: dict[str, Any] | None = None,
        active_suspensions: list[dict] | None = None,
    ) -> NoTradeResult:
        """Evaluate all No-Trade gates for a single instrument.

        Args:
            alpha_signal: Alpha signal dict from AlphaComposer
            regime_state: Current regime state
            data_quality: Optional quality report dict
            liquidity_volume: Average daily volume
            bars_history: Number of bars of history available
            latest_data_date: Date of most recent data
            event_risk: Whether there's an upcoming event
            model_agreement: Fraction of models that agree (0.0 to 1.0)
            instrument_status: Dict from DataStorage.get_instrument_status() with keys:
                status, listing_date, delisting_date, ipo_date, lock_up_end_date
            active_suspensions: List of active suspension dicts for this ticker

        Returns:
            NoTradeResult with decision and gate details.
        """
        gates_failed = []
        gates_passed = []
        reason_codes = []

        # Gate 1: Regime blocklist
        if regime_state in self.config.regime_blocklist:
            gates_failed.append("REGIME_BLOCKED")
            reason_codes.append(f"REGIME_BLOCKED: regime '{regime_state}' dalam blocklist")
        else:
            gates_passed.append("REGIME_BLOCKED")

        # Gate 2: Confidence
        confidence = alpha_signal.get("confidence", 0.0)
        if confidence < self.config.min_confidence:
            gates_failed.append("LOW_CONFIDENCE")
            reason_codes.append(f"LOW_CONFIDENCE: {confidence:.4f} < {self.config.min_confidence}")
        else:
            gates_passed.append("LOW_CONFIDENCE")

        # Gate 3: Composite alpha
        composite_alpha = alpha_signal.get("composite_alpha", 0.0)
        if composite_alpha < self.config.min_composite_alpha:
            gates_failed.append("LOW_ALPHA")
            reason_codes.append(f"LOW_ALPHA: {composite_alpha:.4f} < {self.config.min_composite_alpha}")
        else:
            gates_passed.append("LOW_ALPHA")

        # Gate 4: Liquidity
        if liquidity_volume is not None and liquidity_volume < self.config.min_liquidity_volume:
            gates_failed.append("LOW_LIQUIDITY")
            reason_codes.append(f"LOW_LIQUIDITY: volume {liquidity_volume} < {self.config.min_liquidity_volume}")
        else:
            gates_passed.append("LOW_LIQUIDITY")

        # Gate 5: History
        if bars_history is not None and bars_history < self.config.min_bars_history:
            gates_failed.append("INSUFFICIENT_HISTORY")
            reason_codes.append(f"INSUFFICIENT_HISTORY: {bars_history} < {self.config.min_bars_history}")
        else:
            gates_passed.append("INSUFFICIENT_HISTORY")

        # Gate 6: Stale data
        if latest_data_date is not None:
            now = datetime.now(UTC)
            if latest_data_date.tzinfo is None:
                latest_data_date = latest_data_date.replace(tzinfo=UTC)
            age_days = (now - latest_data_date).days
            if age_days > self.config.max_stale_days:
                gates_failed.append("STALE_DATA")
                reason_codes.append(f"STALE_DATA: data {age_days} hari lalu > {self.config.max_stale_days}")
            else:
                gates_passed.append("STALE_DATA")
        else:
            gates_passed.append("STALE_DATA")

        # Gate 7: Event risk
        if event_risk:
            gates_failed.append("EVENT_RISK")
            reason_codes.append("EVENT_RISK: event mendatang dalam window berisiko")
        else:
            gates_passed.append("EVENT_RISK")

        # Gate 8: Model agreement
        if model_agreement < self.config.min_model_agreement:
            gates_failed.append("MODEL_DISAGREEMENT")
            reason_codes.append(f"MODEL_DISAGREEMENT: agreement {model_agreement:.2f} < {self.config.min_model_agreement}")
        else:
            gates_passed.append("MODEL_DISAGREEMENT")

        # Gate 9: Data quality
        if data_quality is not None:
            if not data_quality.get("passed", True):
                gates_failed.append("DATA_QUALITY_FAIL")
                issues = data_quality.get("issues", [])
                reason_codes.append(f"DATA_QUALITY_FAIL: {', '.join(issues[:3])}")
            else:
                gates_passed.append("DATA_QUALITY_FAIL")
        else:
            gates_passed.append("DATA_QUALITY_FAIL")

        # Gate 10: Instrument delisted
        if instrument_status is not None:
            inst_status = instrument_status.get("status", "active")
            if inst_status == "delisted":
                gates_failed.append("DELISTED")
                reason_codes.append(f"DELISTED: ticker status is 'delisted'")
            else:
                gates_passed.append("DELISTED")

            # Gate 11: IPO lock-up period
            lock_up_end = instrument_status.get("lock_up_end_date")
            ipo_date = instrument_status.get("ipo_date") or instrument_status.get("listing_date")
            now_str = datetime.now(UTC).strftime("%Y-%m-%d")
            if lock_up_end and now_str < lock_up_end:
                gates_failed.append("IPO_LOCKUP")
                reason_codes.append(f"IPO_LOCKUP: lock-up ends {lock_up_end}, today is {now_str}")
            elif ipo_date and self.config.ipo_min_history_days > 0 and bars_history is not None:
                if bars_history < self.config.ipo_min_history_days:
                    gates_failed.append("IPO_INSUFFICIENT_HISTORY")
                    reason_codes.append(
                        f"IPO_INSUFFICIENT_HISTORY: only {bars_history} bars since IPO "
                        f"({ipo_date}), need {self.config.ipo_min_history_days}"
                    )
                else:
                    gates_passed.append("IPO_LOCKUP")
            else:
                gates_passed.append("IPO_LOCKUP")
        else:
            gates_passed.append("DELISTED")
            gates_passed.append("IPO_LOCKUP")

        # Gate 12: Active trading suspension
        if active_suspensions:
            gates_failed.append("SUSPENDED")
            reasons = [s.get("reason", "unknown") for s in active_suspensions[:3]]
            reason_codes.append(f"SUSPENDED: active suspension ({', '.join(reasons)})")
        else:
            gates_passed.append("SUSPENDED")

        decision = "NO_TRADE" if gates_failed else "PROCEED"

        return NoTradeResult(
            instrument_id=alpha_signal.get("instrument_id", 0),
            symbol=alpha_signal.get("symbol", ""),
            decision=decision,
            gates_failed=gates_failed,
            gates_passed=gates_passed,
            reason_codes=reason_codes,
        )

    def evaluate_batch(
        self,
        alpha_signals: list[dict[str, Any]],
        regime_state: str,
        data_provider: dict[int, dict[str, Any]] | None = None,
    ) -> list[NoTradeResult]:
        """Evaluate No-Trade gates for a batch of instruments.

        Args:
            alpha_signals: List of alpha signal dicts
            regime_state: Current regime state
            data_provider: Optional dict mapping instrument_id -> context

        Returns:
            List of NoTradeResult.
        """
        results = []
        for signal in alpha_signals:
            inst_id = signal.get("instrument_id", 0)
            ctx = (data_provider or {}).get(inst_id, {})

            result = self.evaluate(
                alpha_signal=signal,
                regime_state=regime_state,
                data_quality=ctx.get("data_quality"),
                liquidity_volume=ctx.get("liquidity_volume"),
                bars_history=ctx.get("bars_history"),
                latest_data_date=ctx.get("latest_data_date"),
                event_risk=ctx.get("event_risk", False),
                model_agreement=ctx.get("model_agreement", 1.0),
                instrument_status=ctx.get("instrument_status"),
                active_suspensions=ctx.get("active_suspensions"),
            )
            results.append(result)

        return results
