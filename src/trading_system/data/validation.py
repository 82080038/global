"""Data Quality Validation Engine (Phase 1).

Jenis validasi:
- Completeness
- Plausibility
- Cross-source (placeholder, karena sumber tunggal)
- Reconciliation (placeholder)
"""

from typing import Any

import pandas as pd

from trading_system.data.contracts import DataQualityReport
from trading_system.data.storage import DataStorage


class DataQualityValidator:
    def __init__(self):
        self.storage = DataStorage()

    def validate(self, df: pd.DataFrame) -> tuple[pd.DataFrame, DataQualityReport]:
        if df.empty:
            return df, DataQualityReport(record_count=0, data_quality_score=0.0, action="pause")

        anomalies = []
        n = len(df)
        score = 100.0

        # 1. Completeness Check
        missing_pct = df.isna().mean().mean() * 100
        if missing_pct > 0:
            score -= missing_pct * 2
            anomalies.append({
                "check": "completeness",
                "detail": f"{missing_pct:.2f}% missing values",
                "severity": "medium",
            })

        # 2. Plausibility Check
        price_cols = ["open", "high", "low", "close"]
        for _, row in df.iterrows():
            for col in price_cols:
                if pd.isna(row.get(col)):
                    continue
                if row.get(col) <= 0:
                    anomalies.append({
                        "check": "plausibility",
                        "detail": f"{col} <= 0 at {row.get('timestamp')}",
                        "severity": "high",
                    })
                    score -= 2.0
                    break

            if row.get("low") > row.get("high"):
                anomalies.append({
                    "check": "plausibility",
                    "detail": f"low > high at {row.get('timestamp')}",
                    "severity": "high",
                })
                score -= 2.0

            if row.get("close") < row.get("low") or row.get("close") > row.get("high"):
                anomalies.append({
                    "check": "plausibility",
                    "detail": f"close di luar high/low at {row.get('timestamp')}",
                    "severity": "high",
                })
                score -= 2.0

        # 3. Volume spike sederhana: bandingkan dengan median
        if "volume" in df.columns and not df["volume"].empty:
            median_vol = df["volume"].median()
            if median_vol > 0:
                spikes = df[df["volume"] > 10 * median_vol]
                if not spikes.empty:
                    anomalies.append({
                        "check": "plausibility",
                        "detail": f"{len(spikes)} volume spikes >10x median",
                        "severity": "low",
                    })
                    score -= 1.0

        # 4. Gap harian sederhana
        if "timestamp" in df.columns:
            df["timestamp_dt"] = pd.to_datetime(df["timestamp"])
            df_sorted = df.sort_values("timestamp_dt")
            if not df_sorted.empty:
                diffs = df_sorted["timestamp_dt"].diff().dt.days.dropna()
                weekend_gaps = (diffs > 5).sum()
                if weekend_gaps:
                    anomalies.append({
                        "check": "completeness",
                        "detail": f"{weekend_gaps} gap >5 hari terdeteksi",
                        "severity": "low",
                    })
                    score -= 0.5

        score = max(0.0, min(100.0, score))

        # Tindakan otomatis
        if score < 70:
            action = "pause"
        elif score < 90:
            action = "flag"
        else:
            action = "accept"

        df = df.copy()
        df["data_quality_score"] = score

        report = DataQualityReport(
            record_count=n,
            data_quality_score=round(score, 2),
            anomalies=anomalies,
            action=action,
        )

        self.storage.audit(
            "data.quality.validation",
            {
                "record_count": n,
                "data_quality_score": score,
                "anomaly_count": len(anomalies),
                "action": action,
            },
        )
        return df, report
