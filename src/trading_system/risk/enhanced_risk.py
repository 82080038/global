"""Enhanced Risk Engine (FF, §4.1).

Adapted from TIP/python/engines/risk_engine.py.
Position sizing, exposure limits, drawdown guard, portfolio construction.
Long-only Indonesia MVP with volatility targeting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np

RISK_VERSION = "1.0"


@dataclass
class RiskConfig:
    max_position_pct: float = 0.10
    max_sector_pct: float = 0.30
    max_portfolio_beta: float = 1.3
    target_volatility: float = 0.15
    max_drawdown_threshold: float = 0.10
    cash_min_pct: float = 0.05
    cash_max_pct: float = 0.50
    stop_loss_pct: float = 0.08
    trailing_stop_pct: float = 0.12
    transaction_cost_bps: float = 15.0
    slippage_bps: float = 10.0
    rebalance_frequency_days: int = 30


@dataclass
class PositionSizing:
    instrument_id: int
    symbol: str
    weight: float
    shares: int
    price: float
    volatility: float
    risk_score: float
    reason_codes: list[str] = field(default_factory=list)


@dataclass
class RiskMetrics:
    portfolio_volatility: float
    portfolio_beta: float
    max_drawdown: float
    cash_allocation: float
    sector_exposure: dict[str, float]
    position_count: int
    gross_exposure: float
    net_exposure: float
    estimated_transaction_cost: float
    reason_codes: list[str] = field(default_factory=list)


class EnhancedRiskEngine:
    """Compute position sizes and portfolio risk metrics.

    Long-only Indonesia MVP with volatility targeting.
    """

    def __init__(
        self,
        config: RiskConfig | None = None,
        risk_version: str = RISK_VERSION,
        as_of: datetime | None = None,
    ):
        self.config = config or RiskConfig()
        self.risk_version = risk_version
        self.as_of = as_of or datetime.now(UTC)

    def size_positions(
        self,
        signals: list[dict[str, Any]],
        total_capital: float,
        volatilities: dict[int, float],
        prices: dict[int, float],
        sector_map: dict[int, str] | None = None,
        regime_state: str = "neutral",
    ) -> list[PositionSizing]:
        """Compute position sizes using volatility targeting."""
        if regime_state in ("crisis", "unknown"):
            cash_pct = self.config.cash_max_pct
        elif regime_state in ("bear", "risk_off"):
            cash_pct = 0.30
        elif regime_state in ("sideways", "neutral"):
            cash_pct = 0.15
        else:
            cash_pct = self.config.cash_min_pct

        investable_capital = total_capital * (1.0 - cash_pct)
        sorted_signals = sorted(signals, key=lambda s: s.get("composite_alpha", 0), reverse=True)

        positions = []
        sector_exposure: dict[str, float] = {}
        remaining_capital = investable_capital

        for signal in sorted_signals:
            inst_id = signal["instrument_id"]
            symbol = signal.get("symbol", "")
            alpha = signal.get("composite_alpha", 0)
            vol = volatilities.get(inst_id, 0.30)
            price = prices.get(inst_id, 0)

            if price <= 0 or vol <= 0:
                continue

            inv_vol = 1.0 / vol
            raw_weight = alpha * inv_vol

            max_weight = min(
                self.config.max_position_pct,
                remaining_capital / total_capital,
            )

            sector = (sector_map or {}).get(inst_id, "default")
            current_sector = sector_exposure.get(sector, 0)
            available_sector = self.config.max_sector_pct - current_sector
            max_weight = min(max_weight, available_sector)

            if max_weight <= 0:
                continue

            weight = min(raw_weight, max_weight)
            if weight <= 0:
                continue

            capital_allocation = weight * total_capital
            shares = int(capital_allocation / price)
            if shares <= 0:
                continue

            actual_weight = (shares * price) / total_capital
            remaining_capital -= shares * price
            sector_exposure[sector] = current_sector + actual_weight
            risk_score = vol * actual_weight

            positions.append(PositionSizing(
                instrument_id=inst_id,
                symbol=symbol,
                weight=round(actual_weight, 6),
                shares=shares,
                price=price,
                volatility=round(vol, 6),
                risk_score=round(risk_score, 6),
                reason_codes=[f"CASH_PCT:{cash_pct:.2f}", f"REGIME:{regime_state}"],
            ))

        return positions

    def compute_risk_metrics(
        self,
        positions: list[PositionSizing],
        total_capital: float,
        sector_map: dict[int, str] | None = None,
        betas: dict[int, float] | None = None,
        current_drawdown: float = 0.0,
    ) -> RiskMetrics:
        """Compute portfolio-level risk metrics."""
        if not positions:
            return RiskMetrics(
                portfolio_volatility=0.0,
                portfolio_beta=0.0,
                max_drawdown=current_drawdown,
                cash_allocation=1.0,
                sector_exposure={},
                position_count=0,
                gross_exposure=0.0,
                net_exposure=0.0,
                estimated_transaction_cost=0.0,
                reason_codes=["NO_POSITIONS"],
            )

        weights = np.array([p.weight for p in positions])
        vols = np.array([p.volatility for p in positions])
        portfolio_vol = float(np.sqrt(np.sum((weights * vols) ** 2)))

        if betas:
            beta_values = np.array([betas.get(p.instrument_id, 1.0) for p in positions])
            portfolio_beta = float(np.sum(weights * beta_values))
        else:
            portfolio_beta = 1.0

        sector_exp: dict[str, float] = {}
        for p in positions:
            sector = (sector_map or {}).get(p.instrument_id, "default")
            sector_exp[sector] = sector_exp.get(sector, 0) + p.weight

        gross_exposure = float(np.sum(weights))
        cash_allocation = 1.0 - gross_exposure

        turnover = gross_exposure
        cost_bps = self.config.transaction_cost_bps + self.config.slippage_bps
        estimated_cost = turnover * total_capital * (cost_bps / 10000.0)

        reason_codes = []
        if current_drawdown > self.config.max_drawdown_threshold:
            reason_codes.append(f"DRAWDOWN_GUARD: drawdown {current_drawdown:.4f} > {self.config.max_drawdown_threshold}")
        if portfolio_beta > self.config.max_portfolio_beta:
            reason_codes.append(f"BETA_GUARD: portfolio beta {portfolio_beta:.4f} > {self.config.max_portfolio_beta}")
        for sector, exp in sector_exp.items():
            if exp > self.config.max_sector_pct:
                reason_codes.append(f"SECTOR_CONCENTRATION: {sector} = {exp:.4f} > {self.config.max_sector_pct}")

        return RiskMetrics(
            portfolio_volatility=round(portfolio_vol, 6),
            portfolio_beta=round(portfolio_beta, 6),
            max_drawdown=round(current_drawdown, 6),
            cash_allocation=round(cash_allocation, 6),
            sector_exposure={k: round(v, 6) for k, v in sector_exp.items()},
            position_count=len(positions),
            gross_exposure=round(gross_exposure, 6),
            net_exposure=round(gross_exposure, 6),
            estimated_transaction_cost=round(estimated_cost, 6),
            reason_codes=reason_codes,
        )

    def check_stops(
        self,
        positions: list[PositionSizing],
        entry_prices: dict[int, float],
        current_prices: dict[int, float],
        highest_prices: dict[int, float] | None = None,
    ) -> list[dict[str, Any]]:
        """Check stop-loss and trailing-stop conditions."""
        stops = []
        for pos in positions:
            inst_id = pos.instrument_id
            entry = entry_prices.get(inst_id, pos.price)
            current = current_prices.get(inst_id, pos.price)
            highest = (highest_prices or {}).get(inst_id, entry)

            if entry <= 0 or current <= 0:
                continue

            loss_pct = (entry - current) / entry
            trailing_drop = (highest - current) / highest if highest > 0 else 0

            if loss_pct >= self.config.stop_loss_pct:
                stops.append({
                    "instrument_id": inst_id,
                    "symbol": pos.symbol,
                    "action": "STOP_LOSS",
                    "loss_pct": round(loss_pct, 6),
                    "reason": f"Stop loss triggered: {loss_pct:.4f} >= {self.config.stop_loss_pct}",
                })
            elif trailing_drop >= self.config.trailing_stop_pct:
                stops.append({
                    "instrument_id": inst_id,
                    "symbol": pos.symbol,
                    "action": "TRAILING_STOP",
                    "trailing_drop": round(trailing_drop, 6),
                    "reason": f"Trailing stop triggered: {trailing_drop:.4f} >= {self.config.trailing_stop_pct}",
                })

        return stops
