"""Pre-Trade Checklist — adaptasi dari pustaka/13-hal-yang-perlu-diperhatikan.md & 16-strategi-mencari-keuntungan.md.

Automated pre-trade checks sebelum eksekusi order:
- Fundamental score check (minimum threshold)
- Liquidity check (volume minimum)
- Position sizing check (risk per trade ≤ 2%)
- Sector concentration check (≤ 30%)
- Free float check (≥ 15% — reformasi 2026)
- Risk/Reward ratio check (≥ 1:2)
- Behavioral risk check
- Gorengan detection check
- Market regime check

Output: list of checks with PASS/FAIL/WARN status and messages.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class ChecklistResult:
    """Single checklist item result."""
    check: str
    status: str  # PASS, FAIL, WARN
    message: str
    value: float | None = None
    threshold: float | None = None


@dataclass
class PreTradeReport:
    """Complete pre-trade checklist report."""
    ticker: str
    checks: list[ChecklistResult] = field(default_factory=list)
    can_proceed: bool = True

    @property
    def fail_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "FAIL")

    @property
    def warn_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "WARN")

    @property
    def pass_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "PASS")

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "can_proceed": self.can_proceed,
            "summary": {
                "pass": self.pass_count,
                "warn": self.warn_count,
                "fail": self.fail_count,
            },
            "checks": [
                {
                    "check": c.check,
                    "status": c.status,
                    "message": c.message,
                    "value": c.value,
                    "threshold": c.threshold,
                }
                for c in self.checks
            ],
        }


def check_fundamental_score(score: float | None, min_score: float = 50.0) -> ChecklistResult:
    """Check if fundamental score meets minimum threshold."""
    if score is None:
        return ChecklistResult(
            check="FUNDAMENTAL_SCORE",
            status="WARN",
            message="Fundamental score tidak tersedia. Lakukan riset manual.",
        )
    if score < min_score:
        return ChecklistResult(
            check="FUNDAMENTAL_SCORE",
            status="FAIL",
            message=f"Fundamental score {score:.0f} < {min_score:.0f}. Fundamental lemah.",
            value=score,
            threshold=min_score,
        )
    return ChecklistResult(
        check="FUNDAMENTAL_SCORE",
        status="PASS",
        message=f"Fundamental score {score:.0f} ≥ {min_score:.0f}.",
        value=score,
        threshold=min_score,
    )


def check_liquidity(df: pd.DataFrame, min_volume: int = 1_000_000, window: int = 30) -> ChecklistResult:
    """Check if stock has sufficient liquidity."""
    if df.empty or len(df) < window:
        return ChecklistResult(
            check="LIQUIDITY",
            status="WARN",
            message="Data tidak cukup untuk evaluasi likuiditas.",
        )
    avg_vol = df["volume"].iloc[-window:].mean()
    if avg_vol < min_volume:
        return ChecklistResult(
            check="LIQUIDITY",
            status="FAIL",
            message=f"Volume rata-rata {avg_vol:,.0f} < {min_volume:,}. Likuiditas sangat rendah — slippage tinggi.",
            value=float(avg_vol),
            threshold=float(min_volume),
        )
    if avg_vol < min_volume * 5:
        return ChecklistResult(
            check="LIQUIDITY",
            status="WARN",
            message=f"Volume {avg_vol:,.0f}. Likuiditas terbatas — hati-hati slippage.",
            value=float(avg_vol),
            threshold=float(min_volume * 5),
        )
    return ChecklistResult(
        check="LIQUIDITY",
        status="PASS",
        message=f"Volume rata-rata {avg_vol:,.0f} ≥ {min_volume:,}. Likuiditas memadai.",
        value=float(avg_vol),
        threshold=float(min_volume),
    )


def check_position_size(
    capital: float,
    entry: float,
    stop_loss: float,
    risk_pct: float = 0.02,
    max_risk_pct: float = 0.02,
) -> ChecklistResult:
    """Check if position size risk is within acceptable limit."""
    risk_amount = capital * risk_pct
    risk_per_share = abs(entry - stop_loss)
    if risk_per_share <= 0:
        return ChecklistResult(
            check="POSITION_SIZE",
            status="FAIL",
            message="Stop loss terlalu dekat dengan entry — risk per share = 0.",
        )
    position_value = (risk_amount / risk_per_share) * entry
    position_pct = position_value / capital if capital > 0 else 0

    if risk_pct > max_risk_pct:
        return ChecklistResult(
            check="POSITION_SIZE",
            status="FAIL",
            message=f"Risk per trade {risk_pct:.1%} > {max_risk_pct:.1%} max. Position size terlalu besar.",
            value=risk_pct,
            threshold=max_risk_pct,
        )
    if position_pct > 0.20:
        return ChecklistResult(
            check="POSITION_SIZE",
            status="WARN",
            message=f"Position value {position_pct:.1%} dari modal. Pertimbangkan diversifikasi.",
            value=position_pct,
            threshold=0.20,
        )
    return ChecklistResult(
        check="POSITION_SIZE",
        status="PASS",
        message=f"Risk per trade {risk_pct:.1%} ≤ {max_risk_pct:.1%}. Position size aman.",
        value=risk_pct,
        threshold=max_risk_pct,
    )


def check_sector_concentration(
    sector: str,
    portfolio_sector_exposure: dict[str, float],
    max_sector: float = 0.30,
) -> ChecklistResult:
    """Check if adding this position would exceed sector concentration limit."""
    current = portfolio_sector_exposure.get(sector, 0.0)
    if current > max_sector:
        return ChecklistResult(
            check="SECTOR_CONCENTRATION",
            status="FAIL",
            message=f"Sektor {sector} exposure {current:.0%} > {max_sector:.0%}. Over-concentrated.",
            value=current,
            threshold=max_sector,
        )
    if current > max_sector * 0.8:
        return ChecklistResult(
            check="SECTOR_CONCENTRATION",
            status="WARN",
            message=f"Sektor {sector} exposure {current:.0%} mendekati limit {max_sector:.0%}.",
            value=current,
            threshold=max_sector,
        )
    return ChecklistResult(
        check="SECTOR_CONCENTRATION",
        status="PASS",
        message=f"Sektor {sector} exposure {current:.0%} ≤ {max_sector:.0%}.",
        value=current,
        threshold=max_sector,
    )


def check_free_float(free_float_pct: float | None, min_free_float: float = 15.0) -> ChecklistResult:
    """Check if free float meets minimum threshold (reformasi 2026: 15%)."""
    if free_float_pct is None:
        return ChecklistResult(
            check="FREE_FLOAT",
            status="WARN",
            message="Data free float tidak tersedia. Cek daftar HSC BEI.",
        )
    if free_float_pct < min_free_float:
        return ChecklistResult(
            check="FREE_FLOAT",
            status="FAIL",
            message=f"Free float {free_float_pct:.1f}% < {min_free_float:.0f}%. "
            f"Harga mudah dimanipulasi — risiko gorengan.",
            value=free_float_pct,
            threshold=min_free_float,
        )
    return ChecklistResult(
        check="FREE_FLOAT",
        status="PASS",
        message=f"Free float {free_float_pct:.1f}% ≥ {min_free_float:.0f}%.",
        value=free_float_pct,
        threshold=min_free_float,
    )


def check_risk_reward(entry: float, stop_loss: float, target: float, min_rr: float = 2.0) -> ChecklistResult:
    """Check if risk/reward ratio meets minimum threshold."""
    risk = abs(entry - stop_loss)
    reward = abs(target - entry)
    if risk <= 0:
        return ChecklistResult(
            check="RISK_REWARD",
            status="FAIL",
            message="Risk = 0. Stop loss sama dengan entry.",
        )
    rr = reward / risk
    if rr < min_rr:
        return ChecklistResult(
            check="RISK_REWARD",
            status="FAIL",
            message=f"R/R {rr:.1f} < {min_rr:.1f}. Reward tidak cukup besar vs risk.",
            value=rr,
            threshold=min_rr,
        )
    return ChecklistResult(
        check="RISK_REWARD",
        status="PASS",
        message=f"R/R {rr:.1f} ≥ {min_rr:.1f}.",
        value=rr,
        threshold=min_rr,
    )


def check_behavioral_risk(df: pd.DataFrame) -> ChecklistResult:
    """Check behavioral risk score from price/volume patterns."""
    from trading_system.analysis.behavioral_risk import assess_behavioral_risk

    if df.empty or len(df) < 60:
        return ChecklistResult(
            check="BEHAVIORAL_RISK",
            status="WARN",
            message="Data tidak cukup untuk behavioral risk assessment.",
        )

    report = assess_behavioral_risk(df)
    if report.has_high_risk:
        return ChecklistResult(
            check="BEHAVIORAL_RISK",
            status="WARN",
            message=f"Behavioral risk score {report.score:.0f}. Bias terdeteksi: "
            f"{', '.join(b.bias_type for b in report.biases)}.",
            value=report.score,
            threshold=50.0,
        )
    if report.score > 40:
        return ChecklistResult(
            check="BEHAVIORAL_RISK",
            status="WARN",
            message=f"Behavioral risk score {report.score:.0f}. Beberapa bias terdeteksi.",
            value=report.score,
            threshold=40.0,
        )
    return ChecklistResult(
        check="BEHAVIORAL_RISK",
        status="PASS",
        message=f"Behavioral risk score {report.score:.0f}. Tidak ada bias signifikan.",
        value=report.score,
        threshold=50.0,
    )


def check_gorengan(
    df: pd.DataFrame,
    pe_ratio: float | None = None,
    roe: float | None = None,
    der: float | None = None,
) -> ChecklistResult:
    """Check if stock shows gorengan patterns."""
    from trading_system.analysis.gorengan_detector import detect_gorengan

    if df.empty or len(df) < 30:
        return ChecklistResult(
            check="GORENGAN",
            status="WARN",
            message="Data tidak cukup untuk gorengan detection.",
        )

    report = detect_gorengan(df, pe_ratio=pe_ratio, roe=roe, der=der)
    if report.is_gorengan:
        return ChecklistResult(
            check="GORENGAN",
            status="FAIL",
            message=f"GORENGAN TERDETEKSI (risk score {report.risk_score:.0f}). "
            f"Harga naik tanpa fundamental — hindari.",
            value=report.risk_score,
            threshold=50.0,
        )
    if report.risk_score > 40:
        return ChecklistResult(
            check="GORENGAN",
            status="WARN",
            message=f"Beberapa flag gorengan terdeteksi (score {report.risk_score:.0f}). Hati-hati.",
            value=report.risk_score,
            threshold=40.0,
        )
    return ChecklistResult(
        check="GORENGAN",
        status="PASS",
        message=f"Tidak ada indikasi gorengan (score {report.risk_score:.0f}).",
        value=report.risk_score,
        threshold=50.0,
    )


def run_pre_trade_checklist(
    ticker: str,
    df: pd.DataFrame,
    entry: float,
    stop_loss: float,
    target: float,
    capital: float,
    risk_pct: float = 0.02,
    fundamental_score: float | None = None,
    free_float_pct: float | None = None,
    sector: str = "unknown",
    portfolio_sector_exposure: dict[str, float] | None = None,
    pe_ratio: float | None = None,
    roe: float | None = None,
    der: float | None = None,
) -> PreTradeReport:
    """Run complete pre-trade checklist.

    Args:
        ticker: Stock ticker symbol.
        df: OHLCV DataFrame with DatetimeIndex.
        entry: Planned entry price.
        stop_loss: Planned stop loss price.
        target: Planned target price.
        capital: Total portfolio capital.
        risk_pct: Risk per trade as fraction of capital.
        fundamental_score: Fundamental analysis score (0-100).
        free_float_pct: Free float percentage.
        sector: Stock sector classification.
        portfolio_sector_exposure: Current sector exposure as fractions of portfolio.
        pe_ratio: P/E ratio for gorengan check.
        roe: ROE percentage for gorengan check.
        der: D/E ratio for gorengan check.

    Returns:
        PreTradeReport with all check results and can_proceed flag.
    """
    checks: list[ChecklistResult] = []

    checks.append(check_fundamental_score(fundamental_score))
    checks.append(check_liquidity(df))
    checks.append(check_position_size(capital, entry, stop_loss, risk_pct))
    checks.append(check_sector_concentration(sector, portfolio_sector_exposure or {}))
    checks.append(check_free_float(free_float_pct))
    checks.append(check_risk_reward(entry, stop_loss, target))
    checks.append(check_behavioral_risk(df))
    checks.append(check_gorengan(df, pe_ratio=pe_ratio, roe=roe, der=der))

    can_proceed = all(c.status != "FAIL" for c in checks)

    return PreTradeReport(ticker=ticker, checks=checks, can_proceed=can_proceed)
