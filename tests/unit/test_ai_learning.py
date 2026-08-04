"""Unit tests for AILearningEngine."""

import json
from unittest.mock import MagicMock

import pandas as pd

from trading_system.ai_learning.engine import REGIME_WEIGHTS, AILearningEngine


class TestAILearningEngine:

    def test_get_factor_weights_no_ticker_returns_regime_weights(self, mock_storage):
        """Without ticker, should return regime-based weights."""
        engine = AILearningEngine(storage=mock_storage)
        weights = engine.get_factor_weights(regime="easing")

        assert weights == REGIME_WEIGHTS["easing"]

    def test_get_factor_weights_unknown_regime_returns_default(self, mock_storage):
        """Unknown regime should fall back to DEFAULT_WEIGHTS."""
        from trading_system.decision.engine import DEFAULT_WEIGHTS

        engine = AILearningEngine(storage=mock_storage)
        weights = engine.get_factor_weights(regime="unknown_regime")

        assert weights == DEFAULT_WEIGHTS

    def test_get_factor_weights_no_history_returns_base(self, mock_storage):
        """No score history should return base regime weights."""
        mock_storage.load_scores.return_value = pd.DataFrame()
        engine = AILearningEngine(storage=mock_storage)
        weights = engine.get_factor_weights(ticker="TEST.JK", regime="neutral")

        # Should return default weights (neutral regime)
        from trading_system.decision.engine import DEFAULT_WEIGHTS
        assert weights == DEFAULT_WEIGHTS

    def test_get_factor_weights_with_history_adjusts(self, mock_storage):
        """Historical scores should adjust weights."""
        scores_df = pd.DataFrame({
            "engine": ["technical", "fundamental", "macro", "global", "relationship", "sentiment"],
            "score": [75, 65, 55, 60, 50, 58],
            "as_of": ["2024-01-01"] * 6,
            "breakdown": [json.dumps({})] * 6,
        })
        mock_storage.load_scores.return_value = scores_df

        engine = AILearningEngine(storage=mock_storage)
        weights = engine.get_factor_weights(ticker="TEST.JK", regime="neutral")

        # Weights should be normalized (sum to 1)
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.01

    def test_get_factor_weights_low_fundamental_coverage_penalized(self, mock_storage):
        """Low data coverage in fundamental should reduce its weight."""
        scores_df = pd.DataFrame({
            "engine": ["technical", "fundamental", "macro", "global", "relationship", "sentiment"],
            "score": [75, 50, 55, 60, 50, 58],
            "as_of": ["2024-01-01"] * 6,
            "breakdown": [
                "{}",
                json.dumps({"_data_coverage": 0.2}),  # Very low coverage
                "{}", "{}", "{}", "{}",
            ],
        })
        mock_storage.load_scores.return_value = scores_df

        engine = AILearningEngine(storage=mock_storage)
        weights = engine.get_factor_weights(ticker="TEST.JK", regime="neutral")

        # Fundamental weight should be reduced compared to default
        from trading_system.decision.engine import DEFAULT_WEIGHTS
        assert weights["fundamental"] < DEFAULT_WEIGHTS["fundamental"]

    def test_feature_importance(self):
        """Feature importance should compute relative weights."""
        engine = AILearningEngine(storage=MagicMock())
        scores = {"technical": 80, "fundamental": 60, "macro": 40}
        importance = engine.feature_importance(scores)

        assert len(importance) == 3
        total = sum(item["importance"] for item in importance)
        assert abs(total - 1.0) < 0.01

    def test_feature_importance_empty(self):
        """Empty scores should return empty list."""
        engine = AILearningEngine(storage=MagicMock())
        importance = engine.feature_importance({})
        assert importance == []

    def test_get_regime_no_ticker(self, mock_storage):
        """No ticker should return neutral regime."""
        engine = AILearningEngine(storage=mock_storage)
        assert engine.get_regime() == "neutral"

    def test_get_regime_no_macro_data(self, mock_storage):
        """No macro data should return neutral regime."""
        mock_storage.load_scores.return_value = pd.DataFrame()
        engine = AILearningEngine(storage=mock_storage)
        assert engine.get_regime("TEST.JK") == "neutral"

    def test_get_regime_from_macro_data(self, mock_storage):
        """Should extract regime from macro breakdown."""
        scores_df = pd.DataFrame({
            "engine": ["macro"],
            "score": [55],
            "as_of": ["2024-01-01"],
            "breakdown": [json.dumps({"regime": "tightening"})],
        })
        mock_storage.load_scores.return_value = scores_df
        engine = AILearningEngine(storage=mock_storage)
        assert engine.get_regime("TEST.JK") == "tightening"

    def test_regime_weights_cover_all_classify_regime_outputs(self):
        """REGIME_WEIGHTS must cover all regimes that classify_regime can produce (§13.4 #6)."""
        expected_regimes = {"easing", "tightening", "growth", "slowdown", "neutral", "unknown"}
        assert expected_regimes.issubset(set(REGIME_WEIGHTS.keys())), (
            f"Missing regimes in REGIME_WEIGHTS: {expected_regimes - set(REGIME_WEIGHTS.keys())}"
        )

    def test_regime_weights_cover_tip_compatible(self):
        """REGIME_WEIGHTS must include risk_on/risk_off for TIP engine compatibility (§13.4 #6)."""
        assert "risk_on" in REGIME_WEIGHTS
        assert "risk_off" in REGIME_WEIGHTS
        assert REGIME_WEIGHTS["risk_on"] is not None
        assert REGIME_WEIGHTS["risk_off"] is not None

    def test_regime_weights_sum_to_one(self):
        """All non-None regime weights should sum to approximately 1.0."""
        for regime, weights in REGIME_WEIGHTS.items():
            if weights is None:
                continue
            total = sum(weights.values())
            assert abs(total - 1.0) < 0.01, f"Regime '{regime}' weights sum to {total}, expected ~1.0"

    def test_macro_regime_map_to_tip_compatible(self):
        """MacroEconomicEngine.map_regime should map internal regimes to TIP-compatible (§13.4 #6)."""
        from trading_system.analysis.macro import MacroEconomicEngine
        engine = MacroEconomicEngine.__new__(MacroEconomicEngine)

        assert engine.map_regime("easing") == "risk_on"
        assert engine.map_regime("growth") == "risk_on"
        assert engine.map_regime("tightening") == "risk_off"
        assert engine.map_regime("slowdown") == "risk_off"
        assert engine.map_regime("neutral") == "neutral"
        assert engine.map_regime("unknown") == "neutral"
        assert engine.map_regime("nonexistent") == "neutral"


class TestTrainLinearRegression:
    """Regression tests for §2.4 SARAN_PENGEMBANGAN.md: non-negative constraint,
    TimeSeriesSplit OOS validation, dan ambang minimal sampel yang dinaikkan."""

    def _build_scores_and_prices(self, n_days, feature_cols, coef_map, seed=0):
        import numpy as np
        rng = np.random.RandomState(seed)
        dates = pd.date_range("2023-01-01", periods=n_days, freq="B")

        scores = {col: rng.uniform(30, 70, n_days) for col in feature_cols}
        forward_return = sum(coef_map.get(col, 0.0) * (scores[col] - 50) for col in feature_cols)
        forward_return += rng.normal(0, 0.001, n_days)

        rows = []
        for col in feature_cols:
            for i, d in enumerate(dates):
                rows.append({"engine": col, "score": scores[col][i], "as_of": d.isoformat(), "breakdown": "{}"})
        scores_df = pd.DataFrame(rows)
        scores_df["timestamp"] = scores_df["as_of"]

        close = 1000 * (1 + pd.Series(forward_return, index=dates)).cumprod().shift(1).fillna(1000)
        price_df = pd.DataFrame({
            "timestamp": dates,
            "close": close.values,
            "open": close.values, "high": close.values, "low": close.values,
            "volume": 1_000_000,
        })
        return scores_df, price_df

    def test_insufficient_data_below_min_samples(self, mock_storage):
        """< 60 sampel harus ditolak (ambang lama 20 dinaikkan ke 60)."""
        feature_cols = ["technical", "fundamental", "macro", "global", "relationship", "sentiment"]
        scores_df, price_df = self._build_scores_and_prices(30, feature_cols, {})
        mock_storage.list_active_equity_tickers.return_value = ["TEST.JK"]
        mock_storage.load_scores.return_value = scores_df
        mock_storage.load_ohlcv.return_value = price_df

        engine = AILearningEngine(storage=mock_storage)
        result = engine.train_linear_regression()

        assert result["status"] == "insufficient_data"

    def test_negative_coefficient_is_clipped_to_zero(self, mock_storage):
        """Faktor yang berkorelasi negatif dengan forward return tidak boleh
        mendapat bobot positif (np.abs() sebelumnya membuang arah koefisien)."""
        feature_cols = ["technical", "fundamental", "macro", "global", "relationship", "sentiment"]
        # 'sentiment' sengaja dibuat berkorelasi NEGATIF kuat dengan forward return
        coef_map = {"technical": 0.01, "sentiment": -0.02}
        scores_df, price_df = self._build_scores_and_prices(120, feature_cols, coef_map)
        mock_storage.list_active_equity_tickers.return_value = ["TEST.JK"]
        mock_storage.load_scores.return_value = scores_df
        mock_storage.load_ohlcv.return_value = price_df
        mock_storage.save_ai_weights = MagicMock()

        engine = AILearningEngine(storage=mock_storage)
        result = engine.train_linear_regression()

        assert result["status"] == "ok"
        assert result["weights"]["sentiment"] == 0.0
        assert result["weights"]["technical"] > 0.0

    def test_oos_r2_score_present_with_enough_samples(self, mock_storage):
        """Dengan cukup sampel, hasil training harus menyertakan oos_r2_score (TimeSeriesSplit)."""
        feature_cols = ["technical", "fundamental", "macro", "global", "relationship", "sentiment"]
        coef_map = {"technical": 0.01}
        scores_df, price_df = self._build_scores_and_prices(150, feature_cols, coef_map)
        mock_storage.list_active_equity_tickers.return_value = ["TEST.JK"]
        mock_storage.load_scores.return_value = scores_df
        mock_storage.load_ohlcv.return_value = price_df
        mock_storage.save_ai_weights = MagicMock()

        engine = AILearningEngine(storage=mock_storage)
        result = engine.train_linear_regression()

        assert result["status"] == "ok"
        assert "oos_r2_score" in result
        assert result["n_splits"] >= 2
