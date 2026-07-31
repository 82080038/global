"""Unit tests for Layer 5: N (Labeling) + S (Deep Learning) + T (Ensemble) + L (Model Registry)."""


import numpy as np
import pandas as pd
import pytest

from trading_system.ai_learning.deep_learning import DeepLearningConfig, DeepLearningModel
from trading_system.ai_learning.ensemble import EnsembleConfig, EnsembleSystem
from trading_system.ai_learning.labeling import (
    LabelingConfig,
    LabelingEngine,
    alpha_adjusted_labels,
    forward_return_labels,
    triple_barrier_labels,
)
from trading_system.ai_learning.model_registry import ModelRegistry


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


class TestLabeling:
    """Tests for N — Alpha-Adjusted Labeling."""

    def test_forward_return_labels(self):
        df = _make_ohlcv(50)
        labels = forward_return_labels(df, periods=5)
        assert len(labels) == 50
        assert labels.isna().sum() == 5  # last 5 are NaN

    def test_triple_barrier_labels(self):
        df = _make_ohlcv(50)
        labels = triple_barrier_labels(df, profit_take_pct=0.05, stop_loss_pct=0.03, max_periods=10)
        assert len(labels) == 50
        valid = labels.dropna()
        assert all(v in [-1.0, 0.0, 1.0] for v in valid)

    def test_alpha_adjusted_labels(self):
        df = _make_ohlcv(50)
        labels = alpha_adjusted_labels(df, forward_periods=5, regime_state="risk_on")
        assert len(labels) == 50
        assert labels.isna().sum() == 5

    def test_alpha_adjusted_crisis_zero(self):
        df = _make_ohlcv(50)
        labels = alpha_adjusted_labels(df, forward_periods=5, regime_state="crisis")
        valid = labels.dropna()
        assert all(v == 0.0 for v in valid)

    def test_labeling_engine(self):
        df = _make_ohlcv(50)
        engine = LabelingEngine()
        result = engine.compute(df, regime_state="neutral")
        assert "forward_return" in result
        assert "triple_barrier" in result
        assert "alpha_adjusted" in result

    def test_labeling_config(self):
        config = LabelingConfig(forward_periods=10, profit_take_pct=0.10)
        assert config.forward_periods == 10
        assert config.profit_take_pct == 0.10


class TestDeepLearning:
    """Tests for S — Deep Learning Models."""

    def test_prepare_sequences(self):
        df = _make_ohlcv(50)
        model = DeepLearningModel(DeepLearningConfig(lookback=10))
        X, y = model._prepare_sequences(df)
        assert X.shape[0] == 40  # 50 - 10
        assert X.shape[1] == 10  # lookback
        assert X.shape[2] == 5   # features
        assert len(y) == 40

    def test_train_predict(self):
        df = _make_ohlcv(100)
        config = DeepLearningConfig(lookback=10, epochs=5, batch_size=16)
        model = DeepLearningModel(config)
        metrics = model.train(df)
        assert "model_type" in metrics
        assert model.is_fitted

        preds = model.predict(df)
        assert len(preds) > 0

    def test_predict_unfitted(self):
        df = _make_ohlcv(50)
        model = DeepLearningModel()
        with pytest.raises(ValueError, match="not fitted"):
            model.predict(df)

    def test_insufficient_data(self):
        df = _make_ohlcv(5)
        model = DeepLearningModel(DeepLearningConfig(lookback=20))
        metrics = model.train(df)
        assert "error" in metrics


class TestEnsemble:
    """Tests for T — Ensemble System."""

    def test_voting(self):
        ens = EnsembleSystem(EnsembleConfig(method="voting"))
        result = ens.combine({"model_a": 0.8, "model_b": 0.6, "model_c": 0.4})
        assert result == pytest.approx(0.6, abs=0.01)

    def test_weighted(self):
        ens = EnsembleSystem(EnsembleConfig(method="weighted", weights={"model_a": 0.5, "model_b": 0.5}))
        result = ens.combine({"model_a": 0.8, "model_b": 0.6})
        assert result == pytest.approx(0.7, abs=0.01)

    def test_weighted_default_fallback(self):
        ens = EnsembleSystem(EnsembleConfig(method="weighted", fallback_weight=1.0))
        result = ens.combine({"model_a": 0.8, "model_b": 0.6})
        assert result == pytest.approx(0.7, abs=0.01)

    def test_update_weights(self):
        ens = EnsembleSystem(EnsembleConfig(method="weighted"))
        ens.update_weights({"model_a": 0.8, "model_b": 0.2})
        assert ens.config.weights["model_a"] == pytest.approx(0.8, abs=0.01)
        assert ens.config.weights["model_b"] == pytest.approx(0.2, abs=0.01)

    def test_combine_batch(self):
        ens = EnsembleSystem(EnsembleConfig(method="voting"))
        preds = {"model_a": [0.8, 0.6], "model_b": [0.4, 0.2]}
        result = ens.combine_batch(preds)
        assert len(result) == 2
        assert result[0] == pytest.approx(0.6, abs=0.01)

    def test_model_agreement(self):
        ens = EnsembleSystem()
        agreement = ens.get_model_agreement({"a": 0.5, "b": 0.3, "c": -0.1})
        assert agreement == pytest.approx(2/3, abs=0.01)

    def test_empty_predictions(self):
        ens = EnsembleSystem()
        assert ens.combine({}) == 0.0


class TestModelRegistry:
    """Tests for L — Model Registry."""

    def _make_registry(self, tmp_path):
        return ModelRegistry(registry_dir=tmp_path / "model_store")

    def test_register_and_load(self, tmp_path):
        registry = self._make_registry(tmp_path)
        model = {"weights": [1, 2, 3]}
        record = registry.register("test_model", "1.0", model, metrics={"sharpe": 1.5})
        assert record.name == "test_model"
        assert record.version == "1.0"
        assert record.status == "experiment"

        loaded = registry.load("test_model", "1.0")
        assert loaded == model

    def test_promote(self, tmp_path):
        registry = self._make_registry(tmp_path)
        registry.register("test_model", "1.0", {"w": 1}, metrics={"sharpe": 1.0})
        registry.register("test_model", "2.0", {"w": 2}, metrics={"sharpe": 1.5})

        registry.promote("test_model", "2.0", "production")
        versions = registry.list_versions("test_model")
        v2 = [v for v in versions if v.version == "2.0"][0]
        assert v2.status == "production"

    def test_promote_demotes_others(self, tmp_path):
        registry = self._make_registry(tmp_path)
        registry.register("m", "1.0", {"w": 1})
        registry.promote("m", "1.0", "production")
        registry.register("m", "2.0", {"w": 2})
        registry.promote("m", "2.0", "production")

        v1 = [v for v in registry.list_versions("m") if v.version == "1.0"][0]
        assert v1.status == "staging"

    def test_load_production(self, tmp_path):
        registry = self._make_registry(tmp_path)
        registry.register("m", "1.0", {"w": 1})
        registry.register("m", "2.0", {"w": 2})
        registry.promote("m", "2.0", "production")
        loaded = registry.load("m")  # no version = production
        assert loaded == {"w": 2}

    def test_compare(self, tmp_path):
        registry = self._make_registry(tmp_path)
        registry.register("m", "1.0", {"w": 1}, metrics={"sharpe": 1.0, "max_dd": 0.15})
        registry.register("m", "2.0", {"w": 2}, metrics={"sharpe": 1.5, "max_dd": 0.10})
        comparison = registry.compare("m", "1.0", "2.0")
        assert comparison["1.0"]["sharpe"] == 1.0
        assert comparison["2.0"]["sharpe"] == 1.5

    def test_get_best_version(self, tmp_path):
        registry = self._make_registry(tmp_path)
        registry.register("m", "1.0", {"w": 1}, metrics={"sharpe": 1.0})
        registry.register("m", "2.0", {"w": 2}, metrics={"sharpe": 1.5})
        registry.register("m", "3.0", {"w": 3}, metrics={"sharpe": 0.8})
        best = registry.get_best_version("m", metric="sharpe")
        assert best == "2.0"

    def test_not_found(self, tmp_path):
        registry = self._make_registry(tmp_path)
        with pytest.raises(KeyError):
            registry.load("nonexistent")

    def test_list_versions_empty(self, tmp_path):
        registry = self._make_registry(tmp_path)
        assert registry.list_versions("nonexistent") == []
