"""Unit tests for Layer 6: C, D, V, H, I, AA, BB, M, Q."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import numpy as np
import pandas as pd

from trading_system.ai_learning.purged_tss import PurgedKFold, walk_forward_indices
from trading_system.ai_learning.walk_forward import WalkForwardConfig, WalkForwardValidator
from trading_system.analysis.attribution import PerformanceAttribution
from trading_system.analysis.cross_asset import CrossAssetEngine
from trading_system.analysis.factor_screener import FactorScreenerService
from trading_system.analysis.lead_lag import LeadLagAnalyzer
from trading_system.analysis.manipulation import (
    check_manipulation,
    detect_pump_dump,
    detect_volume_anomaly,
    detect_wash_trading,
)
from trading_system.risk.corr_sizing import CorrelationPositionSizing
from trading_system.risk.expectancy import TradeResult, TradingExpectancy


def _make_ohlcv(n=100, start_price=1000):
    dates = pd.bdate_range(start="2024-01-01", periods=n)
    rng = np.random.RandomState(42)
    returns = rng.normal(0.001, 0.015, n)
    close = start_price * np.cumprod(1 + returns)
    high = close * (1 + np.abs(rng.normal(0, 0.01, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.01, n)))
    open_ = np.roll(close, 1)
    open_[0] = start_price
    volume = rng.randint(1_000_000, 50_000_000, n).astype(float)
    return pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close,
        "volume": volume,
    }, index=dates)


class TestPurgedKFold:
    """Tests for C — Purged Time Series Split."""

    def test_split_basic(self):
        df = _make_ohlcv(100)
        kf = PurgedKFold(n_splits=5, purge_days=3, embargo_days=2)
        splits = list(kf.split(df))
        assert len(splits) == 5
        for train_idx, test_idx in splits:
            assert len(train_idx) > 0
            assert len(test_idx) > 0
            # No overlap
            assert set(train_idx) & set(test_idx) == set()

    def test_purge_removes_nearby(self):
        df = _make_ohlcv(100)
        kf = PurgedKFold(n_splits=5, purge_days=5, embargo_days=3)
        splits = list(kf.split(df))
        for train_idx, test_idx in splits:
            test_min = min(test_idx)
            test_max = max(test_idx)
            # No train indices within purge window of test
            for idx in train_idx:
                assert not (test_min - 5 <= idx <= test_max + 5)

    def test_walk_forward_indices(self):
        splits = walk_forward_indices(500, train_size=200, test_size=50, step_size=50)
        assert len(splits) > 0
        for train_range, test_range in splits:
            assert train_range.stop == test_range.start


class TestWalkForward:
    """Tests for D — Walk-Forward Validator."""

    def test_split_rolling(self):
        v = WalkForwardValidator(WalkForwardConfig(train_size=100, test_size=20, step_size=20, expanding=False))
        splits = v.split(500)
        assert len(splits) > 0
        for train_range, test_range in splits:
            assert len(train_range) == 100

    def test_split_expanding(self):
        v = WalkForwardValidator(WalkForwardConfig(train_size=100, test_size=20, step_size=20, expanding=True))
        splits = v.split(500)
        assert len(splits) > 0
        # In expanding mode, first fold has 100 train, second has 120, etc.
        first_train = splits[0][0]
        second_train = splits[1][0]
        assert len(second_train) > len(first_train)

    def test_validate(self):
        df = _make_ohlcv(300)
        v = WalkForwardValidator(WalkForwardConfig(train_size=100, test_size=20, step_size=20))

        def train_fn(data):
            return {"mean": data["close"].mean()}

        def predict_fn(model, data):
            return np.full(len(data), model["mean"])

        result = v.validate(df, train_fn, predict_fn, target_col="close")
        assert "n_folds" in result
        assert "oos_mse" in result
        assert result["n_folds"] > 0


class TestTradingExpectancy:
    """Tests for V — Trading Expectancy."""

    def test_all_wins(self):
        trades = [
            TradeResult("A", 100, 110, 100),
            TradeResult("B", 200, 220, 50),
        ]
        result = TradingExpectancy.compute(trades)
        assert result["win_rate"] == 1.0
        assert result["avg_loss"] == 0.0
        assert result["expectancy"] > 0

    def test_all_losses(self):
        trades = [
            TradeResult("A", 100, 90, 100),
            TradeResult("B", 200, 180, 50),
        ]
        result = TradingExpectancy.compute(trades)
        assert result["win_rate"] == 0.0
        assert result["avg_win"] == 0.0
        assert result["expectancy"] < 0

    def test_mixed(self):
        trades = [
            TradeResult("A", 100, 110, 100),
            TradeResult("B", 200, 190, 50),
            TradeResult("C", 150, 165, 80),
            TradeResult("D", 120, 108, 60),
        ]
        result = TradingExpectancy.compute(trades)
        assert result["win_rate"] == 0.5
        assert result["rrr"] > 0
        assert result["total_trades"] == 4

    def test_empty(self):
        result = TradingExpectancy.compute([])
        assert result["total_trades"] == 0
        assert result["win_rate"] == 0.0

    def test_short_trade(self):
        trades = [TradeResult("A", 100, 90, 100, side="short")]
        result = TradingExpectancy.compute(trades)
        assert result["win_rate"] == 1.0  # short profit when price falls
        assert result["expectancy"] > 0


class TestPerformanceAttribution:
    """Tests for H — Performance Attribution."""

    def test_attribute_by_sector(self):
        returns = pd.DataFrame({
            "A": [0.01, 0.02, 0.03],
            "B": [-0.01, 0.01, 0.02],
            "C": [0.02, 0.03, 0.04],
        })
        weights = {"A": 0.4, "B": 0.3, "C": 0.3}
        sector_map = {"A": "finance", "B": "finance", "C": "tech"}
        result = PerformanceAttribution.attribute_by_sector(returns, weights, sector_map)
        assert "finance" in result
        assert "tech" in result

    def test_compute_attribution(self):
        rng = np.random.RandomState(42)
        portfolio = pd.Series(rng.normal(0.001, 0.02, 100))
        benchmark = pd.Series(rng.normal(0.0005, 0.015, 100))
        result = PerformanceAttribution.compute_attribution(portfolio, benchmark)
        assert "alpha" in result
        assert "beta" in result
        assert "tracking_error" in result
        assert "information_ratio" in result


class TestCorrelationPositionSizing:
    """Tests for I — Correlation Position Sizing."""

    def test_correlation_penalty(self):
        corr = np.array([[1.0, 0.9], [0.9, 1.0]])
        weights = np.array([0.5, 0.5])
        penalty = CorrelationPositionSizing.correlation_penalty(corr, weights)
        assert penalty < 1.0  # high correlation = penalty

    def test_correlation_penalty_uncorrelated(self):
        corr = np.array([[1.0, 0.0], [0.0, 1.0]])
        weights = np.array([0.5, 0.5])
        penalty = CorrelationPositionSizing.correlation_penalty(corr, weights)
        assert penalty == 1.0  # no correlation = no penalty

    def test_risk_parity_weights(self):
        vols = np.array([0.15, 0.30, 0.20])
        corr = np.eye(3)
        weights = CorrelationPositionSizing.risk_parity_weights(vols, corr)
        assert abs(sum(weights) - 1.0) < 0.01
        # Lower vol asset should get higher weight
        assert weights[0] > weights[1]

    def test_diversification_ratio(self):
        vols = np.array([0.20, 0.20])
        corr = np.array([[1.0, 0.5], [0.5, 1.0]])
        weights = np.array([0.5, 0.5])
        dr = CorrelationPositionSizing.diversification_ratio(weights, vols, corr)
        assert dr > 1.0  # diversified

    def test_adjust_weights(self):
        corr = np.array([[1.0, 0.9], [0.9, 1.0]])
        weights = np.array([0.5, 0.5])
        adjusted = CorrelationPositionSizing.adjust_weights_for_correlation(weights, corr, max_correlation=0.7)
        assert abs(sum(adjusted) - 1.0) < 0.01


class TestCrossAsset:
    """Tests for AA — Cross-Asset Engine."""

    def test_compute_no_data(self):
        storage = MagicMock()
        storage.load_ohlcv.return_value = pd.DataFrame()
        engine = CrossAssetEngine(storage=storage)
        result = engine.compute()
        assert result["regime"] == "neutral"

    def test_compute_with_data(self):
        storage = MagicMock()
        df = _make_ohlcv(100)
        df.index = pd.bdate_range(start=datetime.now() - timedelta(days=100), periods=100)
        storage.load_ohlcv.return_value = df
        engine = CrossAssetEngine(storage=storage)
        result = engine.compute()
        assert "regime" in result
        assert "config_version" in result
        assert "pairs" in result["metadata"]


class TestLeadLag:
    """Tests for BB — Lead-Lag Analyzer."""

    def test_analyze_pair_short_data(self):
        analyzer = LeadLagAnalyzer(min_bars=30)
        leader = np.random.randn(10)
        follower = np.random.randn(10)
        result = analyzer.analyze_pair(leader, follower)
        assert not result["significant"]
        assert result["direction"] == "none"

    def test_analyze_pair_synchronous(self):
        analyzer = LeadLagAnalyzer(min_bars=30, corr_threshold=0.3)
        returns = np.random.randn(100)
        result = analyzer.analyze_pair(returns, returns, "A", "B")
        assert result["direction"] in ("synchronous", "leader_leads", "follower_leads")

    def test_analyze_multiple(self):
        analyzer = LeadLagAnalyzer(min_bars=30)
        data = {"A": np.random.randn(100), "B": np.random.randn(100)}
        results = analyzer.analyze_multiple(data, [("A", "B")])
        assert len(results) == 1

    def test_analyze_multiple_missing(self):
        analyzer = LeadLagAnalyzer()
        data = {"A": np.random.randn(50)}
        results = analyzer.analyze_multiple(data, [("A", "B")])
        assert results[0]["direction"] == "none"


class TestManipulation:
    """Tests for M — Manipulation Detection."""

    def test_clean_data_no_flags(self):
        df = _make_ohlcv(100)
        report = check_manipulation(df, "TEST.JK")
        assert report.risk_score < 50  # clean data shouldn't trigger high risk

    def test_volume_anomaly_detected(self):
        df = _make_ohlcv(100)
        df.loc[df.index[50], "volume"] = df["volume"].median() * 20  # huge spike
        flags = detect_volume_anomaly(df, threshold=5.0)
        assert len(flags) > 0
        assert any(f.check == "volume_anomaly" for f in flags)

    def test_pump_dump_detected(self):
        df = _make_ohlcv(50)
        # Create pump at bar 20: rise 20% then fall 15%
        df.iloc[15:20, df.columns.get_loc("close")] = np.linspace(1000, 1200, 5)
        df.iloc[20:25, df.columns.get_loc("close")] = np.linspace(1200, 1020, 5)
        flags = detect_pump_dump(df, rise_threshold=0.15, fall_threshold=0.10)
        assert len(flags) > 0

    def test_wash_trading_detected(self):
        df = _make_ohlcv(100)
        df.loc[df.index[50], "volume"] = df["volume"].median() * 10
        df.loc[df.index[50], "close"] = df["close"].iloc[49]  # no price change
        flags = detect_wash_trading(df, vol_threshold=3.0, price_threshold=0.01)
        assert len(flags) > 0

    def test_report_to_dict(self):
        df = _make_ohlcv(100)
        report = check_manipulation(df, "TEST.JK")
        d = report.to_dict()
        assert d["symbol"] == "TEST.JK"
        assert "risk_score" in d
        assert "has_danger" in d


class TestFactorScreener:
    """Tests for Q — Factor Screener Service."""

    def test_screen(self):
        storage = MagicMock()
        df = _make_ohlcv(260)
        df.index = pd.bdate_range(start=datetime.now() - timedelta(days=260), periods=260)
        storage.load_ohlcv.return_value = df
        storage.list_tickers.return_value = ["TEST.JK", "ABC.JK"]

        from trading_system.analysis.factor_engine import FactorEngine
        engine = FactorEngine(storage=storage)
        screener = FactorScreenerService(engine)
        result = screener.screen(top_n=5, tickers=["TEST.JK", "ABC.JK"])
        assert "results" in result
        assert "screened_count" in result
        assert result["universe_size"] == 2

    def test_explain(self):
        storage = MagicMock()
        df = _make_ohlcv(260)
        df.index = pd.bdate_range(start=datetime.now() - timedelta(days=260), periods=260)
        storage.load_ohlcv.return_value = df
        storage.list_tickers.return_value = ["TEST.JK"]

        from trading_system.analysis.factor_engine import FactorEngine
        engine = FactorEngine(storage=storage)
        screener = FactorScreenerService(engine)
        result = screener.explain("TEST.JK", tickers=["TEST.JK"])
        assert result["found"] is True
        assert "factors" in result

    def test_explain_not_found(self):
        storage = MagicMock()
        storage.load_ohlcv.return_value = pd.DataFrame()
        storage.list_tickers.return_value = []

        from trading_system.analysis.factor_engine import FactorEngine
        engine = FactorEngine(storage=storage)
        screener = FactorScreenerService(engine)
        result = screener.explain("NONEXIST", tickers=["NONEXIST"])
        assert result["found"] is False
