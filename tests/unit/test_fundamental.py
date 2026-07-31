"""Unit tests for FundamentalAnalysisEngine."""

import pytest
from unittest.mock import patch, MagicMock

from trading_system.analysis.fundamental import FundamentalAnalysisEngine


class TestFundamentalAnalysisEngine:

    def test_compute_score_with_all_data(self):
        """Score should be 0-100 when all fundamental data is available."""
        engine = FundamentalAnalysisEngine("TEST.JK")
        ratios = {
            "PER": 15.0,
            "PBV": 1.5,
            "ROE": 18.0,
            "DER": 0.5,
            "eps_growth": 10.0,
            "revenue_growth": 8.0,
            "dividend_yield": 2.0,
        }
        score, breakdown, coverage = engine.compute_score(ratios)

        assert 0 <= score <= 100
        assert coverage == 1.0  # All 5 components present
        assert "PER" in breakdown
        assert "PBV" in breakdown
        assert "ROE" in breakdown
        assert "DER" in breakdown
        assert "growth" in breakdown
        assert breakdown["_data_coverage"] == 1.0
        assert breakdown["_missing"] == []

    def test_compute_score_with_partial_data(self):
        """Score should be normalized over available components only, not filled with 12.5."""
        engine = FundamentalAnalysisEngine("TEST.JK")
        ratios = {
            "PER": 15.0,
            "PBV": None,
            "ROE": 18.0,
            "DER": None,
            "eps_growth": None,
            "revenue_growth": None,
        }
        score, breakdown, coverage = engine.compute_score(ratios)

        assert 0 <= score <= 100
        assert coverage == 0.4  # 2 out of 5
        assert "PER" in breakdown
        assert "ROE" in breakdown
        assert "PBV" not in breakdown  # Missing data should NOT be in breakdown
        assert "DER" not in breakdown
        assert "growth" not in breakdown
        assert breakdown["_data_coverage"] == 0.4
        assert set(breakdown["_missing"]) == {"PBV", "DER", "growth"}

    def test_compute_score_with_no_data(self):
        """Score should be 0 when no fundamental data is available."""
        engine = FundamentalAnalysisEngine("TEST.JK")
        ratios = {
            "PER": None,
            "PBV": None,
            "ROE": None,
            "DER": None,
            "eps_growth": None,
            "revenue_growth": None,
        }
        score, breakdown, coverage = engine.compute_score(ratios)

        assert score == 0.0
        assert coverage == 0.0
        assert breakdown["_data_coverage"] == 0.0

    def test_compute_score_low_coverage_penalized(self):
        """Score should be penalized when data coverage < 60%."""
        engine = FundamentalAnalysisEngine("TEST.JK")
        ratios = {
            "PER": 10.0,  # Good PER
            "PBV": None,
            "ROE": None,
            "DER": None,
            "eps_growth": None,
            "revenue_growth": None,
        }
        score, breakdown, coverage = engine.compute_score(ratios)

        # Coverage is 0.2 (1/5), which is < 0.6, so score is penalized
        assert coverage == 0.2
        # Score should be reduced: raw_score / max_available * 100 * (0.2/0.6)
        # raw = 25 - (10/5) = 23, max = 25, so (23/25)*100 * (0.2/0.6) = 92 * 0.333 = 30.67
        assert score < 50  # Should be significantly penalized

    def test_analyze_no_ticker_returns_error(self):
        """Analyze without ticker should return error."""
        engine = FundamentalAnalysisEngine()
        result = engine.analyze()
        assert result["status"] == "error"
        assert "No ticker" in result["message"]

    @patch("trading_system.analysis.fundamental.yf")
    def test_analyze_no_data_returns_warning(self, mock_yf):
        """Analyze with no yfinance data should return failed with null score and weight_multiplier 0."""
        mock_ticker = MagicMock()
        mock_ticker.info = {}
        mock_ticker.financials = None
        mock_ticker.balance_sheet = None
        mock_ticker.cashflow = None
        mock_yf.Ticker.return_value = mock_ticker

        engine = FundamentalAnalysisEngine("EMPTY.JK")
        result = engine.analyze()

        assert result["status"] == "failed"
        assert result["score"] is None
        assert result["weight_multiplier"] == 0.0
