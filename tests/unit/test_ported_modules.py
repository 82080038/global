"""Tests for ported modules: regime, kelly, tax, red_flags, screener."""

import numpy as np
import pandas as pd
import pytest

from trading_system.analysis.regime import detect_regime, regime_to_multiplier, REGIME_MULTIPLIERS
from trading_system.risk.kelly import (
    calculate_kelly_criterion,
    calculate_position_size_kelly,
    calculate_kelly_from_history,
    KellyResult,
)
from trading_system.execution.tax import (
    TaxRates,
    calculate_buy_costs,
    calculate_sell_costs,
    calculate_dividend_tax,
    calculate_trade_result,
    calculate_effective_rate,
)
from trading_system.analysis.red_flags import (
    RedFlag,
    EarningsQualityMetrics,
    BalanceSheetHealth,
    calculate_earnings_quality_metrics,
    calculate_balance_sheet_health,
    detect_earnings_quality_red_flags,
    detect_balance_sheet_red_flags,
    detect_governance_red_flags,
    detect_all_red_flags,
    calculate_red_flag_score,
    get_red_flag_summary,
)
from trading_system.analysis.screener import (
    screen_universe,
    technical_template,
    momentum_template,
    TEMPLATES,
)


class TestRegime:
    def test_shock_when_vix_above_35(self):
        assert detect_regime(vix=40, ihsg_close=7000, ihsg_sma_200=6500, avg_correlation=0.3) == "shock"

    def test_volatile_when_vix_above_25(self):
        assert detect_regime(vix=30, ihsg_close=7000, ihsg_sma_200=6500, avg_correlation=0.3) == "volatile"

    def test_trending_when_above_sma_and_low_correlation(self):
        assert detect_regime(vix=15, ihsg_close=7000, ihsg_sma_200=6500, avg_correlation=0.3) == "trending"

    def test_neutral_fallback(self):
        assert detect_regime(vix=15, ihsg_close=6000, ihsg_sma_200=6500, avg_correlation=0.3) == "neutral"

    def test_regime_to_multiplier(self):
        assert regime_to_multiplier("trending") == 1.0
        assert regime_to_multiplier("shock") == 0.0
        assert regime_to_multiplier("neutral") == 0.7


class TestKelly:
    def test_kelly_criterion_basic(self):
        result = calculate_kelly_criterion(win_rate=0.6, avg_win=0.05, avg_loss=0.03)
        assert result.kelly_fraction > 0
        assert result.kelly_fraction <= 1.0
        assert result.half_kelly == result.kelly_fraction / 2
        assert result.quarter_kelly == result.kelly_fraction / 4

    def test_kelly_negative_edge_returns_zero(self):
        result = calculate_kelly_criterion(win_rate=0.2, avg_win=0.01, avg_loss=0.05)
        assert result.kelly_fraction == 0

    def test_kelly_raises_on_zero_loss(self):
        with pytest.raises(ValueError):
            calculate_kelly_criterion(win_rate=0.6, avg_win=0.05, avg_loss=0)

    def test_position_size_caps_at_max(self):
        result = calculate_position_size_kelly(
            capital=1_000_000, kelly_fraction=0.8, entry_price=1000, max_position_pct=0.25
        )
        assert result["position_value"] <= 250_000
        assert result["position_size"] <= 250

    def test_kelly_from_history(self):
        trades = [
            {"pnl": 0.05}, {"pnl": -0.02}, {"pnl": 0.03}, {"pnl": -0.01}, {"pnl": 0.04},
        ]
        result = calculate_kelly_from_history(trades)
        assert isinstance(result, KellyResult)
        assert result.win_rate == 0.6

    def test_kelly_from_history_empty_raises(self):
        with pytest.raises(ValueError):
            calculate_kelly_from_history([])


class TestTax:
    def test_buy_costs(self):
        costs = calculate_buy_costs(price=8000, position_size=100)
        assert costs.gross_amount == 800_000
        assert costs.broker_fee > 0
        assert costs.transaction_tax == 0  # No tax on buy
        assert costs.net_amount > costs.gross_amount

    def test_sell_costs_includes_transaction_tax(self):
        costs = calculate_sell_costs(price=9000, position_size=100)
        assert costs.gross_amount == 900_000
        assert costs.transaction_tax > 0  # 0.1% PPh
        assert costs.net_amount < costs.gross_amount

    def test_dividend_tax(self):
        result = calculate_dividend_tax(dividend_per_share=100, position_size=1000)
        assert result.gross_dividend == 100_000
        assert result.dividend_tax == 10_000  # 10%
        assert result.net_dividend == 90_000

    def test_trade_result(self):
        result = calculate_trade_result(entry_price=8000, exit_price=9000, position_size=100)
        assert result.gross_pnl == 100_000
        assert result.net_pnl < result.gross_pnl  # Costs reduce PnL
        assert result.net_pnl_pct > 0

    def test_effective_rate(self):
        rates = calculate_effective_rate(entry_price=8000, exit_price=9000, position_size=100)
        assert rates["buy_effective_rate"] > 0
        assert rates["sell_effective_rate"] > rates["buy_effective_rate"]  # Sell has tax
        assert rates["total_costs"] > 0


class TestRedFlags:
    def test_earnings_quality_metrics(self):
        metrics = calculate_earnings_quality_metrics(
            operating_cash_flow=800, net_income=1000, total_assets=5000,
            accounts_receivable=200, revenue=2000, cost_of_goods_sold=1200, inventory=300,
        )
        assert metrics.cash_conversion_ratio == 0.8
        assert metrics.accrual_ratio is not None
        assert metrics.days_sales_outstanding is not None
        assert metrics.inventory_turnover is not None

    def test_balance_sheet_health(self):
        health = calculate_balance_sheet_health(
            current_assets=500, current_liabilities=300, total_debt=400,
            total_equity=600, goodwill=50, total_assets=1000, short_term_debt=200,
        )
        assert health.current_ratio is not None
        assert health.debt_to_equity is not None

    def test_low_cash_conversion_flag(self):
        metrics = EarningsQualityMetrics(cash_conversion_ratio=0.5, accrual_ratio=0.05)
        flags = detect_earnings_quality_red_flags(metrics, revenue_growth=0.1, receivables_growth=0.05, inventory_growth=0.05)
        assert any(f.flag_type == "low_cash_conversion" for f in flags)

    def test_high_accruals_flag(self):
        metrics = EarningsQualityMetrics(accrual_ratio=0.15)
        flags = detect_earnings_quality_red_flags(metrics, revenue_growth=0.1, receivables_growth=0.05, inventory_growth=0.05)
        assert any(f.flag_type == "high_accruals" for f in flags)

    def test_high_debt_to_equity_flag(self):
        health = BalanceSheetHealth(debt_to_equity=3.0)
        flags = detect_balance_sheet_red_flags(health, debt_growth=0.1)
        assert any(f.flag_type == "high_debt_to_equity" for f in flags)

    def test_frequent_auditor_changes_flag(self):
        flags = detect_governance_red_flags(
            auditor_changes=4, related_party_transactions=100, pledging_shares=0.1, independent_directors_ratio=0.4
        )
        assert any(f.flag_type == "frequent_auditor_changes" for f in flags)

    def test_detect_all_red_flags(self):
        metrics = EarningsQualityMetrics(cash_conversion_ratio=0.5)
        health = BalanceSheetHealth(debt_to_equity=3.0)
        flags = detect_all_red_flags(
            metrics, health,
            revenue_growth=0.1, receivables_growth=0.05, inventory_growth=0.05,
            debt_growth=0.1, auditor_changes=4, related_party_transactions=100,
            pledging_shares=0.1, independent_directors_ratio=0.4,
        )
        assert "earnings_quality" in flags
        assert "balance_sheet" in flags
        assert "governance" in flags

    def test_red_flag_score(self):
        flags = {
            "earnings_quality": [RedFlag("test1", "high", "test")],
            "balance_sheet": [RedFlag("test2", "medium", "test"), RedFlag("test3", "low", "test")],
            "governance": [],
        }
        scores = calculate_red_flag_score(flags)
        assert scores["earnings_quality"] == 3
        assert scores["balance_sheet"] == 3
        assert scores["governance"] == 0
        assert scores["total"] == 6

    def test_summary_no_flags(self):
        summary = get_red_flag_summary({"earnings_quality": [], "balance_sheet": []})
        assert "tidak ada" in summary.lower()

    def test_summary_with_flags(self):
        flags = {
            "earnings_quality": [RedFlag("test", "high", "Test flag")],
            "balance_sheet": [],
        }
        summary = get_red_flag_summary(flags)
        assert "1 red flags" in summary
        assert "HIGH" in summary


class TestScreener:
    def _make_features_df(self):
        dates = pd.date_range("2024-01-01", periods=5)
        return pd.DataFrame({
            "date": dates,
            "ticker": ["BBCA"] * 5,
            "close": [8000, 8050, 8100, 8150, 8200],
            "sma_50": [7900, 7950, 8000, 8050, 8100],
            "sma_200": [7800, 7850, 7900, 7950, 8000],
            "rsi_14": [45, 50, 55, 60, 65],
            "adx_14": [25, 28, 30, 32, 35],
            "volume": [1e6, 2e6, 3e6, 4e6, 5e6],
            "volume_sma_20": [1e6] * 5,
            "bb_lower": [7800, 7850, 7900, 7950, 8000],
            "macd_hist": [10, 20, 30, 40, 50],
        })

    def test_technical_template(self):
        df = self._make_features_df()
        result = technical_template(df)
        assert not result.empty
        assert "score" in result.columns

    def test_momentum_template(self):
        df = self._make_features_df()
        result = momentum_template(df)
        assert not result.empty
        assert "score" in result.columns

    def test_value_template_no_fundamentals(self):
        df = self._make_features_df()
        result = screen_universe(df, template="value")
        assert result.empty  # No per/roe/der columns

    def test_screen_universe_unknown_template_raises(self):
        df = self._make_features_df()
        with pytest.raises(ValueError):
            screen_universe(df, template="nonexistent")

    def test_screen_universe_empty_df(self):
        result = screen_universe(pd.DataFrame(), template="technical")
        assert result.empty

    def test_screen_universe_returns_ranked(self):
        df = self._make_features_df()
        df2 = df.copy()
        df2["ticker"] = ["TLKM"] * 5
        df2["rsi_14"] = [60, 62, 64, 66, 68]
        combined = pd.concat([df, df2], ignore_index=True)
        result = screen_universe(combined, template="technical")
        assert "rank" in result.columns
        assert len(result) >= 1
