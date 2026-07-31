"""Tests for MonitoringEngine — system health checks."""

from unittest.mock import MagicMock

from trading_system.monitoring.engine import MonitoringEngine


def test_monitoring_engine_name():
    engine = MonitoringEngine(storage=MagicMock())
    assert engine.name == "monitoring"


def test_monitoring_health_ok():
    storage = MagicMock()
    storage.get_source_health.return_value = MagicMock(empty=True)
    storage.list_tickers.return_value = ["BBCA.JK", "TLKM.JK"]
    storage.load_scores.return_value = MagicMock(empty=True)
    engine = MonitoringEngine(storage=storage)
    result = engine.health()
    assert "status" in result
    assert "timestamp" in result
