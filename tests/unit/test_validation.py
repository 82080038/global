"""Unit tests for DataQualityValidator."""

from unittest.mock import MagicMock, patch

import pandas as pd

from trading_system.data.validation import DataQualityValidator


class TestDataQualityValidator:
    """Test the tiered validation system."""

    @patch("trading_system.data.validation.DataStorage")
    def test_clean_data_gets_gold_tier(self, mock_storage_cls):
        """Data with no anomalies should get 'accept' action and 'gold' tier."""
        mock_storage = MagicMock()
        mock_storage_cls.return_value = mock_storage

        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=100, freq="B").astype(str),
            "open": [100.0] * 100,
            "high": [105.0] * 100,
            "low": [95.0] * 100,
            "close": [102.0] * 100,
            "volume": [1000000.0] * 100,
        })

        validator = DataQualityValidator()
        clean, report = validator.validate(df)

        assert report.data_quality_score >= 90
        assert report.action == "accept"
        assert report.tier == "gold"

    @patch("trading_system.data.validation.DataStorage")
    def test_missing_data_gets_silver_tier(self, mock_storage_cls):
        """Data with ~8% missing values should get 'flag' action and 'silver' tier."""
        mock_storage = MagicMock()
        mock_storage_cls.return_value = mock_storage

        n = 100
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="B").astype(str),
            "open": [100.0] * n,
            "high": [105.0] * n,
            "low": [95.0] * n,
            "close": [102.0] * n,
            "volume": [1000000.0] * n,
        })
        # Need >5% missing to get score <90. 6 cols * 100 rows = 600 cells, 5% = 30.
        # Set 16 rows * 2 cols = 32 cells to get 5.33% missing -> score 89.33
        df.loc[0:15, "close"] = None
        df.loc[0:15, "open"] = None

        validator = DataQualityValidator()
        clean, report = validator.validate(df)

        assert 70 <= report.data_quality_score < 90
        assert report.action == "flag"
        assert report.tier == "silver"

    @patch("trading_system.data.validation.DataStorage")
    def test_poor_data_gets_bronze_tier(self, mock_storage_cls):
        """Data with ~15% missing values should get 'delayed_review' action and 'bronze' tier."""
        mock_storage = MagicMock()
        mock_storage_cls.return_value = mock_storage

        n = 100
        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="B").astype(str),
            "open": [100.0] * n,
            "high": [105.0] * n,
            "low": [95.0] * n,
            "close": [102.0] * n,
            "volume": [1000000.0] * n,
        })
        # Need >15% missing to get score <70. 6 cols * 100 rows = 600 cells, 15% = 90.
        # Set 31 rows * 3 cols = 93 cells to get 15.5% missing -> score 69.0
        df.loc[0:30, "close"] = None
        df.loc[0:30, "open"] = None
        df.loc[0:30, "high"] = None

        validator = DataQualityValidator()
        clean, report = validator.validate(df)

        assert 50 <= report.data_quality_score < 70
        assert report.action == "delayed_review"
        assert report.tier == "bronze"

    @patch("trading_system.data.validation.DataStorage")
    def test_empty_dataframe_gets_pause(self, mock_storage_cls):
        """Empty DataFrame should get 'pause' action."""
        mock_storage = MagicMock()
        mock_storage_cls.return_value = mock_storage

        validator = DataQualityValidator()
        clean, report = validator.validate(pd.DataFrame())

        assert report.data_quality_score == 0.0
        assert report.action == "pause"
        assert report.tier == "reject"

    @patch("trading_system.data.validation.DataStorage")
    def test_negative_prices_detected(self, mock_storage_cls):
        """Negative prices should be flagged as anomalies."""
        mock_storage = MagicMock()
        mock_storage_cls.return_value = mock_storage

        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=10, freq="B").astype(str),
            "open": [100.0] * 10,
            "high": [105.0] * 10,
            "low": [95.0] * 10,
            "close": [-1.0] * 10,  # Negative close
            "volume": [1000000.0] * 10,
        })

        validator = DataQualityValidator()
        clean, report = validator.validate(df)

        assert any(a["check"] == "plausibility" for a in report.anomalies)
        assert report.data_quality_score < 90

    @patch("trading_system.data.validation.DataStorage")
    def test_duplicate_timestamps_detected(self, mock_storage_cls):
        """Duplicate timestamps should be flagged by TIP-derived check."""
        mock_storage = MagicMock()
        mock_storage_cls.return_value = mock_storage

        ts = list(pd.date_range("2024-01-01", periods=10, freq="B").astype(str))
        ts.append(ts[0])  # duplicate
        df = pd.DataFrame({
            "ticker": ["BBCA.JK"] * 11,
            "timestamp": ts,
            "open": [100.0] * 11,
            "high": [105.0] * 11,
            "low": [95.0] * 11,
            "close": [102.0] * 11,
            "volume": [1000000.0] * 11,
        })

        validator = DataQualityValidator()
        clean, report = validator.validate(df)

        assert any(a["check"] == "tip_quality" and "duplicate" in a["detail"] for a in report.anomalies)
        assert report.data_quality_score < 100

    @patch("trading_system.data.validation.DataStorage")
    def test_abnormal_returns_detected(self, mock_storage_cls):
        """Abnormal returns (>25% daily move) should be flagged."""
        mock_storage = MagicMock()
        mock_storage_cls.return_value = mock_storage

        n = 20
        closes = [100.0] * n
        closes[-1] = 150.0  # 50% jump on last day
        df = pd.DataFrame({
            "ticker": ["BBCA.JK"] * n,
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="B").astype(str),
            "open": [100.0] * n,
            "high": [105.0] * (n - 1) + [155.0],
            "low": [95.0] * (n - 1) + [145.0],
            "close": closes,
            "volume": [1000000.0] * n,
        })

        validator = DataQualityValidator()
        clean, report = validator.validate(df)

        assert any(a["check"] == "tip_quality" and "abnormal" in a["detail"] for a in report.anomalies)
