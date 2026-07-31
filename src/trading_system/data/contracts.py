"""Pydantic data contracts."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class OHLCVRecord(BaseModel):
    ticker: str
    asset_class: str = "equity"
    exchange: str = "IDX"
    timestamp: datetime
    timeframe: str = "1d"
    open: float
    high: float
    low: float
    close: float
    volume: float
    adjusted_close: float
    source: str
    ingested_at: datetime | None = None
    data_quality_score: float | None = None


class DataSourceHealth(BaseModel):
    source: str
    last_success: datetime | None = None
    last_error: datetime | None = None
    status: str = "unknown"  # ok, degraded, down


class DataQualityReport(BaseModel):
    record_count: int
    data_quality_score: float  # 0-100
    anomalies: list[dict[str, Any]] = []
    action: str = "accept"  # accept, flag, delayed_review, pause
    tier: str = "gold"  # gold (>=90), silver (70-89), bronze (50-69), reject (<50)
