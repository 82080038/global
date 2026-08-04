"""Strategy Selector — adaptasi dari pustaka/16-strategi-mencari-keuntungan.md.

Memilih strategi optimal berdasarkan profil investor:
- Modal (capital)
- Toleransi risiko (risk_tolerance: low/moderate/high)
- Waktu tersedia (hours_per_week)
- Timeframe investasi
- Tujuan (growth/income/stability)

Strategi yang dipilih menentukan alokasi portfolio dan parameter risk management.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class InvestorProfile:
    """Investor profile for strategy selection."""
    capital: float
    risk_tolerance: str = "moderate"  # low, moderate, high
    hours_per_week: float = 2.0
    timeframe: str = "medium"  # short, medium, long
    goal: str = "growth"  # growth, income, stability
    age: int | None = None
    has_emergency_fund: bool = True
    uses_cold_money: bool = True


@dataclass
class Strategy:
    """Selected investment strategy."""
    name: str
    allocation: dict[str, float] = field(default_factory=dict)
    expected_return: str = ""
    risk_level: str = ""
    time_commitment: str = ""
    description: str = ""


def select_strategy(profile: InvestorProfile) -> list[Strategy]:
    """Select optimal strategy(ies) based on investor profile.

    Returns a list of strategies, ordered by priority.
    """
    strategies: list[Strategy] = []

    if profile.capital < 1_000_000:
        strategies.append(Strategy(
            name="DCA_BLUE_CHIP",
            allocation={"blue_chip_dca": 1.0},
            expected_return="8-12% p.a.",
            risk_level="Low",
            time_commitment="30 min/bulan",
            description="Dollar cost averaging ke saham blue chip atau reksa dana indeks. "
            "Cocok untuk modal kecil — fokus disiplin menabung.",
        ))
    elif profile.capital < 10_000_000:
        strategies.append(Strategy(
            name="DIVERSIFIED_DCA",
            allocation={"blue_chip": 0.5, "growth": 0.3, "dividend": 0.2},
            expected_return="10-15% p.a.",
            risk_level="Low-Medium",
            time_commitment="2-4 jam/minggu",
            description="Diversifikasi 3-5 saham + DCA rutin. Kombinasi blue chip, growth, dan dividend.",
        ))
    elif profile.capital < 50_000_000:
        strategies.append(Strategy(
            name="LAYERED_DIVIDEND_SWING",
            allocation={"dividend_core": 0.5, "growth": 0.2, "swing": 0.15, "opportunistic": 0.05, "cash": 0.10},
            expected_return="12-18% p.a.",
            risk_level="Medium",
            time_commitment="3-5 jam/minggu",
            description="Layered approach: dividen core + growth + swing trading. "
            "Cash reserve untuk opportunity.",
        ))
    else:
        strategies.append(Strategy(
            name="FULL_FIVE_LAYER",
            allocation={"core": 0.55, "growth": 0.18, "swing": 0.12, "opportunistic": 0.08, "cash": 0.07},
            expected_return="15-20% p.a.",
            risk_level="Medium-High",
            time_commitment="5-10 jam/minggu",
            description="Full five-layer system: Core portfolio + Growth + Swing + Opportunistic + Cash reserve. "
            "Untuk modal ≥ Rp 50 juta dengan risk management ketat.",
        ))

    if profile.risk_tolerance == "low":
        strategies.append(Strategy(
            name="DIVIDEND_INVESTING",
            allocation={"dividend_aristocrat": 0.6, "high_yield": 0.3, "cash": 0.1},
            expected_return="8-11% p.a.",
            risk_level="Low-Medium",
            time_commitment="1-2 jam/bulan",
            description="Dividend investing — saham dividen konsisten dan growing. "
            "Passive income dengan DRIP (dividend reinvestment).",
        ))
    elif profile.risk_tolerance == "high":
        strategies.append(Strategy(
            name="GROWTH_INVESTING",
            allocation={"growth_stocks": 0.7, "swing": 0.2, "cash": 0.1},
            expected_return="15-25% p.a.",
            risk_level="Medium-High",
            time_commitment="4-8 jam/bulan",
            description="Growth investing — perusahaan dengan pertumbuhan tinggi. "
            "Valuasi premium acceptable jika growth story intact.",
        ))

    if profile.hours_per_week < 2:
        strategies.append(Strategy(
            name="BUY_AND_HOLD",
            allocation={"blue_chip": 0.7, "dividend": 0.3},
            expected_return="12-15% p.a.",
            risk_level="Low-Medium",
            time_commitment="2-4 jam/bulan",
            description="Buy and hold — beli saham berkualitas, tahan jangka panjang. "
            "Time in the market > timing the market.",
        ))
    elif profile.hours_per_week > 10:
        strategies.append(Strategy(
            name="SWING_TRADING",
            allocation={"swing": 0.6, "core": 0.3, "cash": 0.1},
            expected_return="5-15% per bulan",
            risk_level="Medium",
            time_commitment="1-2 jam/hari",
            description="Swing trading — manfaatkan 'ayunan' harga 2-14 hari. "
            "Butuh disiplin dan risk management ketat.",
        ))

    if profile.goal == "income":
        strategies.append(Strategy(
            name="DIVIDEND_GROWTH_PORTFOLIO",
            allocation={"consumer_staples": 0.4, "financials": 0.25, "infrastructure": 0.2, "healthcare": 0.15},
            expected_return="10-12% p.a. (yield 3.5-4.5% + growth 6-8%)",
            risk_level="Low-Medium",
            time_commitment="1-2 jam/bulan",
            description="Dividend growth portfolio — passive income dari dividen yang tumbuh setiap tahun. "
            "Cocok untuk pensiunan atau investor income.",
        ))
    elif profile.goal == "stability":
        strategies.append(Strategy(
            name="CONSERVATIVE_MIX",
            allocation={"blue_chip": 0.3, "bonds": 0.6, "cash": 0.1},
            expected_return="7-10% p.a.",
            risk_level="Low",
            time_commitment="1-2 jam/bulan",
            description="Conservative mix — saham blue chip + obligasi + kas. "
            "Stabilitas modal prioritized.",
        ))

    return strategies


def get_risk_profile_params(risk_tolerance: str) -> dict:
    """Get risk profile parameters based on tolerance level."""
    profiles = {
        "low": {
            "max_drawdown": 0.10,
            "risk_per_trade": 0.01,
            "allocation_equity": 0.30,
            "allocation_bond": 0.60,
            "allocation_cash": 0.10,
            "timeframe": "5-10 tahun",
        },
        "moderate": {
            "max_drawdown": 0.20,
            "risk_per_trade": 0.02,
            "allocation_equity": 0.60,
            "allocation_bond": 0.30,
            "allocation_cash": 0.10,
            "timeframe": "3-10 tahun",
        },
        "high": {
            "max_drawdown": 0.35,
            "risk_per_trade": 0.03,
            "allocation_equity": 0.85,
            "allocation_bond": 0.10,
            "allocation_cash": 0.05,
            "timeframe": "3+ tahun",
        },
    }
    return profiles.get(risk_tolerance, profiles["moderate"])
