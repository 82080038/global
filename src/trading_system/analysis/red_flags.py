"""Fundamental red flags detection — adaptasi dari pasar_modal/src/features/red_flags.py.

Deteksi red flags kesehatan keuangan perusahaan: earnings quality,
balance sheet health, dan corporate governance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class RedFlag:
    """Representasi sebuah red flag."""

    flag_type: str
    severity: str  # low, medium, high, critical
    description: str
    value: Optional[float] = None
    threshold: Optional[float] = None


@dataclass
class EarningsQualityMetrics:
    """Metrics untuk kualitas earnings."""

    cash_conversion_ratio: Optional[float] = None
    accrual_ratio: Optional[float] = None
    days_sales_outstanding: Optional[float] = None
    inventory_turnover: Optional[float] = None


@dataclass
class BalanceSheetHealth:
    """Metrics untuk kesehatan neraca."""

    current_ratio: Optional[float] = None
    debt_to_equity: Optional[float] = None
    goodwill_ratio: Optional[float] = None
    short_term_debt_ratio: Optional[float] = None


def calculate_earnings_quality_metrics(
    operating_cash_flow: float,
    net_income: float,
    total_assets: float,
    accounts_receivable: float,
    revenue: float,
    cost_of_goods_sold: float,
    inventory: float,
) -> EarningsQualityMetrics:
    """Hitung metrics kualitas earnings."""
    cash_conversion_ratio = operating_cash_flow / net_income if net_income != 0 else None
    accrual_ratio = (net_income - operating_cash_flow) / total_assets if total_assets != 0 else None
    days_sales_outstanding = (accounts_receivable / revenue) * 365 if revenue != 0 else None
    inventory_turnover = cost_of_goods_sold / inventory if inventory != 0 else None

    return EarningsQualityMetrics(
        cash_conversion_ratio=cash_conversion_ratio,
        accrual_ratio=accrual_ratio,
        days_sales_outstanding=days_sales_outstanding,
        inventory_turnover=inventory_turnover,
    )


def calculate_balance_sheet_health(
    current_assets: float,
    current_liabilities: float,
    total_debt: float,
    total_equity: float,
    goodwill: float,
    total_assets: float,
    short_term_debt: float,
) -> BalanceSheetHealth:
    """Hitung metrics kesehatan neraca."""
    current_ratio = current_assets / current_liabilities if current_liabilities != 0 else None
    debt_to_equity = total_debt / total_equity if total_equity != 0 else None
    goodwill_ratio = goodwill / total_assets if total_assets != 0 else None
    short_term_debt_ratio = short_term_debt / total_debt if total_debt != 0 else None

    return BalanceSheetHealth(
        current_ratio=current_ratio,
        debt_to_equity=debt_to_equity,
        goodwill_ratio=goodwill_ratio,
        short_term_debt_ratio=short_term_debt_ratio,
    )


def detect_earnings_quality_red_flags(
    metrics: EarningsQualityMetrics,
    revenue_growth: float,
    receivables_growth: float,
    inventory_growth: float,
) -> list[RedFlag]:
    """Deteksi red flags terkait kualitas earnings."""
    flags = []

    if metrics.cash_conversion_ratio is not None and metrics.cash_conversion_ratio < 0.8:
        flags.append(RedFlag(
            flag_type="low_cash_conversion",
            severity="high",
            description=f"Cash conversion ratio {metrics.cash_conversion_ratio:.2f} < 0.8. Earnings mungkin tidak didukung oleh cash flow.",
            value=metrics.cash_conversion_ratio,
            threshold=0.8,
        ))

    if metrics.accrual_ratio is not None and metrics.accrual_ratio > 0.1:
        flags.append(RedFlag(
            flag_type="high_accruals",
            severity="high",
            description=f"Accrual ratio {metrics.accrual_ratio:.2f} > 0.1. Tinggi accruals mungkin indikasi earnings manipulation.",
            value=metrics.accrual_ratio,
            threshold=0.1,
        ))

    if metrics.days_sales_outstanding is not None and metrics.days_sales_outstanding > 90:
        flags.append(RedFlag(
            flag_type="high_dso",
            severity="medium",
            description=f"Days Sales Outstanding {metrics.days_sales_outstanding:.0f} hari > 90. Masalah collection accounts receivable.",
            value=metrics.days_sales_outstanding,
            threshold=90,
        ))

    if receivables_growth > revenue_growth + 0.1:
        flags.append(RedFlag(
            flag_type="receivables_growth_exceeds_revenue",
            severity="high",
            description=f"Receivables growth {receivables_growth:.1%} > revenue growth {revenue_growth:.1%}. Mungkin indikasi revenue recognition agresif.",
            value=receivables_growth,
            threshold=revenue_growth + 0.1,
        ))

    if inventory_growth > revenue_growth + 0.2:
        flags.append(RedFlag(
            flag_type="inventory_growth_exceeds_sales",
            severity="medium",
            description=f"Inventory growth {inventory_growth:.1%} > sales growth {revenue_growth:.1%}. Mungkin indikasi overstocking atau demand drop.",
            value=inventory_growth,
            threshold=revenue_growth + 0.2,
        ))

    if metrics.inventory_turnover is not None and metrics.inventory_turnover < 4:
        flags.append(RedFlag(
            flag_type="low_inventory_turnover",
            severity="medium",
            description=f"Inventory turnover {metrics.inventory_turnover:.2f} < 4. Slow-moving inventory.",
            value=metrics.inventory_turnover,
            threshold=4,
        ))

    return flags


def detect_balance_sheet_red_flags(
    health: BalanceSheetHealth,
    debt_growth: float,
) -> list[RedFlag]:
    """Deteksi red flags terkait kesehatan neraca."""
    flags = []

    if health.current_ratio is not None and health.current_ratio < 1.0:
        flags.append(RedFlag(
            flag_type="low_current_ratio",
            severity="high",
            description=f"Current ratio {health.current_ratio:.2f} < 1.0. Liquidity problem.",
            value=health.current_ratio,
            threshold=1.0,
        ))

    if health.debt_to_equity is not None and health.debt_to_equity > 2.0:
        flags.append(RedFlag(
            flag_type="high_debt_to_equity",
            severity="high",
            description=f"Debt-to-equity {health.debt_to_equity:.2f} > 2.0. High leverage risk.",
            value=health.debt_to_equity,
            threshold=2.0,
        ))

    if debt_growth > 0.3:
        flags.append(RedFlag(
            flag_type="increasing_debt",
            severity="medium",
            description=f"Debt growth {debt_growth:.1%} > 30%. Debt terus meningkat.",
            value=debt_growth,
            threshold=0.3,
        ))

    if health.goodwill_ratio is not None and health.goodwill_ratio > 0.2:
        flags.append(RedFlag(
            flag_type="high_goodwill",
            severity="medium",
            description=f"Goodwill ratio {health.goodwill_ratio:.2f} > 20%. Mungkin indikasi overpriced acquisitions.",
            value=health.goodwill_ratio,
            threshold=0.2,
        ))

    if health.short_term_debt_ratio is not None and health.short_term_debt_ratio > 0.5:
        flags.append(RedFlag(
            flag_type="high_short_term_debt",
            severity="high",
            description=f"Short-term debt ratio {health.short_term_debt_ratio:.2f} > 50%. Refinancing risk tinggi.",
            value=health.short_term_debt_ratio,
            threshold=0.5,
        ))

    return flags


def detect_governance_red_flags(
    auditor_changes: int,
    related_party_transactions: float,
    pledging_shares: float,
    independent_directors_ratio: float,
) -> list[RedFlag]:
    """Deteksi red flags terkait corporate governance."""
    flags = []

    if auditor_changes > 2:
        flags.append(RedFlag(
            flag_type="frequent_auditor_changes",
            severity="high",
            description=f"Auditor changes {auditor_changes} > 2 dalam 5 tahun. Indikasi masalah governance.",
            value=float(auditor_changes),
            threshold=2.0,
        ))

    if related_party_transactions > 1000:
        flags.append(RedFlag(
            flag_type="large_related_party_transactions",
            severity="high",
            description=f"Related-party transactions Rp {related_party_transactions:.0f} juta > Rp 1 miliar. Indikasi conflict of interest.",
            value=related_party_transactions,
            threshold=1000.0,
        ))

    if pledging_shares > 0.3:
        flags.append(RedFlag(
            flag_type="high_pledging_shares",
            severity="medium",
            description=f"Pledging shares {pledging_shares:.1%} > 30%. Indikasi financial distress pemegang saham.",
            value=pledging_shares,
            threshold=0.3,
        ))

    if independent_directors_ratio < 0.3:
        flags.append(RedFlag(
            flag_type="low_independent_directors",
            severity="medium",
            description=f"Independent directors ratio {independent_directors_ratio:.1%} < 30%. Weak corporate governance.",
            value=independent_directors_ratio,
            threshold=0.3,
        ))

    return flags


def detect_all_red_flags(
    earnings_metrics: EarningsQualityMetrics,
    balance_sheet_health: BalanceSheetHealth,
    revenue_growth: float,
    receivables_growth: float,
    inventory_growth: float,
    debt_growth: float,
    auditor_changes: int,
    related_party_transactions: float,
    pledging_shares: float,
    independent_directors_ratio: float,
) -> dict[str, list[RedFlag]]:
    """Deteksi semua red flags dari berbagai kategori."""
    return {
        "earnings_quality": detect_earnings_quality_red_flags(
            earnings_metrics, revenue_growth, receivables_growth, inventory_growth
        ),
        "balance_sheet": detect_balance_sheet_red_flags(balance_sheet_health, debt_growth),
        "governance": detect_governance_red_flags(
            auditor_changes, related_party_transactions, pledging_shares, independent_directors_ratio
        ),
    }


def calculate_red_flag_score(flags: dict[str, list[RedFlag]]) -> dict[str, int]:
    """Hitung skor red flag per kategori dan total."""
    severity_weights = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    scores = {}
    for category, flag_list in flags.items():
        category_score = sum(severity_weights.get(flag.severity, 0) for flag in flag_list)
        scores[category] = category_score
    scores["total"] = sum(scores.values())
    return scores


def get_red_flag_summary(flags: dict[str, list[RedFlag]]) -> str:
    """Generate summary text untuk red flags."""
    total_flags = sum(len(flag_list) for flag_list in flags.values())
    if total_flags == 0:
        return "Tidak ada red flags terdeteksi."

    summary_parts = [f"Total {total_flags} red flags terdeteksi:\n"]
    for category, flag_list in flags.items():
        if flag_list:
            summary_parts.append(f"\n{category.replace('_', ' ').title()} ({len(flag_list)}):")
            for flag in flag_list:
                summary_parts.append(f"  - [{flag.severity.upper()}] {flag.description}")

    return "\n".join(summary_parts)
