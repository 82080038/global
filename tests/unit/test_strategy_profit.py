"""Tests for strategy selector and profit tracker modules."""

from __future__ import annotations

import pytest

from trading_system.portfolio.profit_tracker import (
    PortfolioProfitReport,
    Position,
    calculate_expectancy,
    calculate_portfolio_profit,
    calculate_position_profit,
)
from trading_system.portfolio.strategy_selector import (
    InvestorProfile,
    Strategy,
    get_risk_profile_params,
    select_strategy,
)


class TestStrategySelector:
    def test_small_capital_gets_dca(self):
        profile = InvestorProfile(capital=500_000, risk_tolerance="low")
        strategies = select_strategy(profile)
        assert any(s.name == "DCA_BLUE_CHIP" for s in strategies)

    def test_medium_capital_gets_layered(self):
        profile = InvestorProfile(capital=25_000_000, risk_tolerance="moderate")
        strategies = select_strategy(profile)
        assert any(s.name == "LAYERED_DIVIDEND_SWING" for s in strategies)

    def test_large_capital_gets_five_layer(self):
        profile = InvestorProfile(capital=100_000_000, risk_tolerance="high")
        strategies = select_strategy(profile)
        assert any(s.name == "FULL_FIVE_LAYER" for s in strategies)

    def test_low_risk_gets_dividend(self):
        profile = InvestorProfile(capital=20_000_000, risk_tolerance="low")
        strategies = select_strategy(profile)
        assert any(s.name == "DIVIDEND_INVESTING" for s in strategies)

    def test_high_risk_gets_growth(self):
        profile = InvestorProfile(capital=20_000_000, risk_tolerance="high")
        strategies = select_strategy(profile)
        assert any(s.name == "GROWTH_INVESTING" for s in strategies)

    def test_low_time_gets_buy_hold(self):
        profile = InvestorProfile(capital=20_000_000, hours_per_week=1)
        strategies = select_strategy(profile)
        assert any(s.name == "BUY_AND_HOLD" for s in strategies)

    def test_high_time_gets_swing(self):
        profile = InvestorProfile(capital=20_000_000, hours_per_week=15)
        strategies = select_strategy(profile)
        assert any(s.name == "SWING_TRADING" for s in strategies)

    def test_income_goal_gets_dividend_growth(self):
        profile = InvestorProfile(capital=20_000_000, goal="income")
        strategies = select_strategy(profile)
        assert any(s.name == "DIVIDEND_GROWTH_PORTFOLIO" for s in strategies)

    def test_stability_goal_gets_conservative(self):
        profile = InvestorProfile(capital=20_000_000, goal="stability")
        strategies = select_strategy(profile)
        assert any(s.name == "CONSERVATIVE_MIX" for s in strategies)

    def test_strategy_has_allocation(self):
        profile = InvestorProfile(capital=100_000_000)
        strategies = select_strategy(profile)
        for s in strategies:
            assert len(s.allocation) > 0
            assert sum(s.allocation.values()) <= 1.01  # Allow rounding

    def test_risk_profile_params(self):
        low = get_risk_profile_params("low")
        assert low["risk_per_trade"] == 0.01
        assert low["allocation_equity"] == 0.30

        high = get_risk_profile_params("high")
        assert high["risk_per_trade"] == 0.03
        assert high["allocation_equity"] == 0.85

        moderate = get_risk_profile_params("moderate")
        assert moderate["risk_per_trade"] == 0.02

        unknown = get_risk_profile_params("unknown")
        assert unknown == moderate


class TestProfitTracker:
    def test_single_position_profit(self):
        pos = Position(ticker="BBCA.JK", shares=1000, avg_cost=7000, dividends_received=250_000)
        breakdown = calculate_position_profit(pos, current_price=8000)
        assert breakdown.capital_gain == 1_000_000
        assert breakdown.capital_gain_pct == pytest.approx(1 / 7, rel=0.01)
        assert breakdown.dividends == 250_000
        assert breakdown.total_return == 1_250_000

    def test_position_with_loss(self):
        pos = Position(ticker="LOSS.JK", shares=1000, avg_cost=8000, dividends_received=0)
        breakdown = calculate_position_profit(pos, current_price=7000)
        assert breakdown.capital_gain == -1_000_000
        assert breakdown.capital_gain_pct < 0
        assert breakdown.total_return < 0

    def test_portfolio_profit(self):
        positions = [
            Position(ticker="BBCA.JK", shares=1000, avg_cost=7000, dividends_received=250_000),
            Position(ticker="TLKM.JK", shares=500, avg_cost=3000, dividends_received=100_000),
        ]
        prices = {"BBCA.JK": 8000, "TLKM.JK": 3500}
        report = calculate_portfolio_profit(positions, prices)
        assert report.total_cost == 8_500_000
        assert report.total_value == 9_750_000
        assert report.total_capital_gain == 1_250_000
        assert report.total_dividends == 350_000
        assert report.total_return == 1_600_000
        assert report.roi > 0
        assert len(report.positions) == 2

    def test_portfolio_to_dict(self):
        positions = [Position(ticker="TEST.JK", shares=100, avg_cost=5000)]
        report = calculate_portfolio_profit(positions, {"TEST.JK": 6000})
        d = report.to_dict()
        assert "total_cost" in d
        assert "total_return" in d
        assert "positions" in d
        assert len(d["positions"]) == 1

    def test_zero_cost_position(self):
        pos = Position(ticker="FREE.JK", shares=0, avg_cost=0)
        breakdown = calculate_position_profit(pos, current_price=5000)
        assert breakdown.capital_gain == 0
        assert breakdown.total_return_pct == 0

    def test_expectancy_profitable(self):
        trades = [2.0, 1.5, -1.0, 3.0, -0.5, 1.0, -1.0, 2.5, -1.0, 1.5]
        result = calculate_expectancy(trades)
        assert result["available"]
        assert result["n_trades"] == 10
        assert "win_rate" in result
        assert "expectancy" in result

    def test_expectancy_insufficient_trades(self):
        trades = [1.0, -0.5, 2.0]
        result = calculate_expectancy(trades, min_sample=10)
        assert not result["available"]

    def test_expectancy_all_wins(self):
        trades = [1.0] * 10
        result = calculate_expectancy(trades)
        assert result["available"]
        assert result["win_rate"] == 1.0
        assert result["avg_loss"] == 0

    def test_expectancy_all_losses(self):
        trades = [-1.0] * 10
        result = calculate_expectancy(trades)
        assert result["available"]
        assert result["win_rate"] == 0.0
        assert result["avg_win"] == 0
        assert not result["profitable"]
