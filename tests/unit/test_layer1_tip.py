"""Unit tests for Data Quality Engine (CC, §4.1) and YFinanceRateLimiter (DD, §4.1)."""

from datetime import datetime, timedelta

import pandas as pd

from trading_system.data.quality import check_quality
from trading_system.data.rate_limit import (
    CircuitState,
    YFinanceRateLimiter,
)


class TestDataQualityEngine:
    """Tests for TIP-derived Data Quality Engine (CC)."""

    def _make_ohlcv(self, n=100, start=None):
        if start is None:
            start = (datetime.now() - timedelta(days=n + 10)).strftime("%Y-%m-%d")
        dates = pd.bdate_range(start=start, periods=n)
        return pd.DataFrame({
            "timestamp": dates,
            "open": [100.0] * n,
            "high": [105.0] * n,
            "low": [99.0] * n,
            "close": [102.0] * n,
            "volume": [1_000_000] * n,
        })

    def test_empty_df(self):
        report = check_quality(pd.DataFrame(), "TEST.JK")
        assert not report.passed
        assert "Tidak ada data" in report.issues
        assert report.rows_checked == 0

    def test_none_df(self):
        report = check_quality(None, "TEST.JK")
        assert not report.passed

    def test_clean_data_passes(self):
        df = self._make_ohlcv(100)
        report = check_quality(df, "TEST.JK")
        assert report.passed
        assert report.rows_checked == 100
        assert report.duplicates == 0
        assert report.zero_prices == 0

    def test_duplicates_detected(self):
        df = self._make_ohlcv(100)
        df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
        report = check_quality(df, "TEST.JK")
        assert report.duplicates == 1
        assert any("duplikat" in i for i in report.issues)

    def test_zero_prices_detected(self):
        df = self._make_ohlcv(100)
        df.loc[5, "close"] = 0
        report = check_quality(df, "TEST.JK")
        assert report.zero_prices == 1
        assert any("harga nol" in i for i in report.issues)

    def test_negative_prices_detected(self):
        df = self._make_ohlcv(100)
        df.loc[5, "open"] = -1
        report = check_quality(df, "TEST.JK")
        assert report.invalid_prices >= 1
        assert any("harga negatif" in i for i in report.issues)

    def test_high_low_violation(self):
        df = self._make_ohlcv(100)
        df.loc[5, "high"] = 50
        df.loc[5, "low"] = 99
        report = check_quality(df, "TEST.JK")
        assert any("high < low" in i for i in report.issues)

    def test_missing_bars_detected(self):
        df = self._make_ohlcv(100)
        df = df.drop(index=[10, 11, 12]).reset_index(drop=True)
        report = check_quality(df, "TEST.JK")
        assert report.missing_bars > 0

    def test_abnormal_returns_detected(self):
        df = self._make_ohlcv(100)
        df.loc[50, "close"] = 500.0  # ~400% jump
        report = check_quality(df, "TEST.JK", abnormal_return_threshold=0.25)
        assert report.abnormal_returns > 0
        assert any("return abnormal" in i for i in report.issues)

    def test_stale_data_detected(self):
        df = self._make_ohlcv(10, start="2020-01-01")
        report = check_quality(df, "TEST.JK", max_stale_days=7)
        assert report.stale_data
        assert any("stale" in i for i in report.issues)

    def test_summary_string(self):
        df = self._make_ohlcv(50)
        report = check_quality(df, "TEST.JK")
        s = report.summary()
        assert "TEST.JK" in s
        assert "LULUS" in s

    def test_to_dict(self):
        df = self._make_ohlcv(50)
        report = check_quality(df, "TEST.JK")
        d = report.to_dict()
        assert d["symbol"] == "TEST.JK"
        assert d["passed"] is True
        assert d["rows_checked"] == 50

    def test_time_column_fallback(self):
        df = self._make_ohlcv(50)
        df = df.rename(columns={"timestamp": "time"})
        report = check_quality(df, "TEST.JK")
        assert report.rows_checked == 50


class TestYFinanceRateLimiter:
    """Tests for TIP-derived YFinanceRateLimiter (DD)."""

    def _make_limiter(self, **kwargs):
        defaults = dict(
            min_delay=0, max_delay=0, max_requests=100,
            window_seconds=3600, max_retries=2, backoff_base=0.01,
            backoff_max=0.1, circuit_threshold=3, circuit_reset_seconds=60,
        )
        defaults.update(kwargs)
        return YFinanceRateLimiter(**defaults)

    def test_successful_execution(self):
        limiter = self._make_limiter()
        result = limiter.execute("TEST.JK", lambda: "data")
        assert result.data == "data"
        assert result.error is None
        assert result.attempts == 1

    def test_retry_on_failure(self):
        limiter = self._make_limiter(max_retries=2)
        call_count = [0]
        def flaky():
            call_count[0] += 1
            if call_count[0] < 2:
                raise Exception("transient")
            return "data"

        result = limiter.execute("TEST.JK", flaky)
        assert result.data == "data"
        assert result.attempts == 2

    def test_all_retries_exhausted(self):
        limiter = self._make_limiter(max_retries=1)
        result = limiter.execute("TEST.JK", lambda: (_ for _ in ()).throw(Exception("fail")))
        assert result.data is None
        assert "fail" in result.error
        assert result.attempts == 2

    def test_circuit_opens_after_threshold(self):
        limiter = self._make_limiter(circuit_threshold=2, max_retries=0)
        limiter.execute("A", lambda: (_ for _ in ()).throw(Exception("e1")))
        limiter.execute("B", lambda: (_ for _ in ()).throw(Exception("e2")))
        assert limiter.circuit_state == CircuitState.OPEN

    def test_circuit_blocks_when_open(self):
        limiter = self._make_limiter(circuit_threshold=1, max_retries=0, circuit_reset_seconds=9999)
        limiter.execute("A", lambda: (_ for _ in ()).throw(Exception("e1")))
        result = limiter.execute("B", lambda: "should_not_reach")
        assert result.data is None
        assert "Circuit breaker" in result.error

    def test_circuit_half_open_after_reset(self):
        limiter = self._make_limiter(circuit_threshold=1, max_retries=0, circuit_reset_seconds=0)
        limiter.execute("A", lambda: (_ for _ in ()).throw(Exception("e1")))
        assert limiter.circuit_state == CircuitState.OPEN
        result = limiter.execute("B", lambda: "recovered")
        assert result.data == "recovered"
        assert limiter.circuit_state == CircuitState.CLOSED

    def test_success_resets_circuit(self):
        limiter = self._make_limiter(circuit_threshold=2, max_retries=0)
        limiter.execute("A", lambda: (_ for _ in ()).throw(Exception("e1")))
        limiter.execute("B", lambda: (_ for _ in ()).throw(Exception("e2")))
        assert limiter.circuit_state == CircuitState.OPEN
        limiter._circuit_opened_at = 0  # force half-open
        result = limiter.execute("C", lambda: "ok")
        assert result.data == "ok"
        assert limiter.circuit_state == CircuitState.CLOSED

    def test_failures_recorded(self):
        limiter = self._make_limiter(max_retries=0)
        limiter.execute("TEST.JK", lambda: (_ for _ in ()).throw(Exception("boom")))
        assert len(limiter.failures) == 1
        assert limiter.failures[0].symbol == "TEST.JK"
        assert "boom" in limiter.failures[0].error

    def test_reset(self):
        limiter = self._make_limiter(max_retries=0)
        limiter.execute("A", lambda: (_ for _ in ()).throw(Exception("e")))
        limiter.reset()
        assert limiter.circuit_state == CircuitState.CLOSED
        assert len(limiter.failures) == 0
        assert len(limiter._request_timestamps) == 0

    def test_from_env(self):
        import os
        os.environ["YFINANCE_MIN_DELAY"] = "0.5"
        os.environ["YFINANCE_MAX_RETRIES"] = "5"
        limiter = YFinanceRateLimiter.from_env()
        assert limiter.min_delay == 0.5
        assert limiter.max_retries == 5
        del os.environ["YFINANCE_MIN_DELAY"]
        del os.environ["YFINANCE_MAX_RETRIES"]

    def test_backoff_computation(self):
        limiter = self._make_limiter(backoff_base=2.0, backoff_max=60.0)
        assert limiter._compute_backoff(1) == 2.0
        assert limiter._compute_backoff(2) == 4.0
        assert limiter._compute_backoff(10) == 60.0  # capped
