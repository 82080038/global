"""Monitoring Engine (Fase 5).

Health check sederhana seluruh engine & sumber data.
"""

from __future__ import annotations

from datetime import UTC, datetime

from trading_system.data.storage import DataStorage


class MonitoringEngine:
    name = "monitoring"

    def __init__(self, storage: DataStorage | None = None):
        self.storage = storage or DataStorage()

    def health(self) -> dict:
        source_df = self.storage.get_source_health()
        tickers = self.storage.list_active_equity_tickers()
        scores_df = self.storage.load_scores()

        now = datetime.now(UTC)
        alerts = []
        for _, row in source_df.iterrows():
            if row.get("status") != "ok":
                alerts.append({"source": row.get("source"), "status": row.get("status"), "last_error": row.get("last_error")})

        return {
            "status": "ok",
            "timestamp": now.isoformat(),
            "sources": source_df.to_dict(orient="records") if not source_df.empty else [],
            "tickers_in_db": tickers,
            "score_count": len(scores_df),
            "alerts": alerts,
        }
