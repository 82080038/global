"""Data Quality Validation Engine.

Jenis validasi:
- Completeness
- Plausibility
- Cross-source: compare adjusted_close vs close for split/dividend detection
- Reconciliation: volume consistency and timestamp continuity
"""

import pandas as pd

from trading_system.data.contracts import DataQualityReport
from trading_system.data.quality import check_quality
from trading_system.data.storage import DataStorage


class DataQualityValidator:
    def __init__(self):
        self.storage = DataStorage()

    def validate(self, df: pd.DataFrame) -> tuple[pd.DataFrame, DataQualityReport]:
        if df.empty:
            return df, DataQualityReport(
                record_count=0,
                data_quality_score=0.0,
                action="pause",
                tier="reject",
            )

        df = df.copy()
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

        # 5. Cross-source check: adjusted_close vs close
        # Detect stock splits and dividends by comparing close and adjusted_close
        if "adjusted_close" in df.columns and "close" in df.columns:
            adj = pd.to_numeric(df["adjusted_close"], errors="coerce")
            cls = pd.to_numeric(df["close"], errors="coerce")
            ratio = adj / cls
            ratio = ratio.replace([float("inf"), float("-inf")], pd.NA).dropna()
            if not ratio.empty:
                # If ratio changes significantly across the dataset, it indicates
                # a split or dividend adjustment — this is expected, not an error
                unique_ratios = ratio.nunique()
                if unique_ratios > 1:
                    # Check for unexpected ratio jumps (potential data error)
                    ratio_diffs = ratio.diff().abs()
                    large_jumps = (ratio_diffs > 0.5).sum()
                    if large_jumps > 0:
                        anomalies.append({
                            "check": "cross_source",
                            "detail": f"{large_jumps} large adjusted_close/close ratio jumps (possible split/dividend or data error)",
                            "severity": "low",
                        })
                        score -= 0.5

                # Check for ratio outside expected range (0.01 to 1.0)
                out_of_range = ((ratio < 0.01) | (ratio > 1.0)).sum()
                if out_of_range > 0:
                    anomalies.append({
                        "check": "cross_source",
                        "detail": f"{out_of_range} records with adjusted_close/close ratio outside [0.01, 1.0]",
                        "severity": "medium",
                    })
                    score -= 1.0

        # 6. Reconciliation: volume consistency
        # Check for zero-volume days (illiquidity flag) and negative volume
        if "volume" in df.columns:
            vol = pd.to_numeric(df["volume"], errors="coerce")
            negative_vol = (vol < 0).sum()
            if negative_vol > 0:
                anomalies.append({
                    "check": "reconciliation",
                    "detail": f"{negative_vol} records with negative volume",
                    "severity": "high",
                })
                score -= 3.0

            zero_vol = (vol == 0).sum()
            zero_pct = (zero_vol / n * 100) if n > 0 else 0
            if zero_pct > 10:
                anomalies.append({
                    "check": "reconciliation",
                    "detail": f"{zero_vol} zero-volume days ({zero_pct:.1f}%) — possible illiquidity",
                    "severity": "low",
                })
                score -= 0.5

        # 7. Reconciliation: OHLCV internal consistency
        # Typical price (H+L+C)/3 should be within [low, high] range
        if all(col in df.columns for col in ["open", "high", "low", "close"]):
            typical_price = (df["high"] + df["low"] + df["close"]) / 3
            out_of_range = ((typical_price < df["low"]) | (typical_price > df["high"])).sum()
            if out_of_range > 0:
                anomalies.append({
                    "check": "reconciliation",
                    "detail": f"{out_of_range} records where typical price outside [low, high]",
                    "severity": "medium",
                })
                score -= 1.0

        # 8. TIP-derived quality checks: duplicates, stale data, abnormal returns
        ticker = df["ticker"].iloc[0] if "ticker" in df.columns else "unknown"
        qr = check_quality(df, symbol=str(ticker))
        if qr.duplicates > 0:
            anomalies.append({
                "check": "tip_quality",
                "detail": f"{qr.duplicates} duplicate timestamps",
                "severity": "medium",
            })
            score -= 2.0
        if qr.stale_data:
            anomalies.append({
                "check": "tip_quality",
                "detail": "data is stale (last bar >7 days ago)",
                "severity": "medium",
            })
            score -= 2.0
        if qr.abnormal_returns > 0:
            anomalies.append({
                "check": "tip_quality",
                "detail": f"{qr.abnormal_returns} abnormal returns (>25% daily move)",
                "severity": "low",
            })
            score -= 1.0

        score = max(0.0, min(100.0, score))

        # Tiered action system:
        # >= 90: accept (gold) — data is clean, use immediately
        # 70-89: flag (silver) — minor issues, use but flag for review
        # 50-69: delayed_review (bronze) — notable issues, queue for manual review
        # < 50: pause (reject) — severe issues, do not use
        if score >= 90:
            action = "accept"
            tier = "gold"
        elif score >= 70:
            action = "flag"
            tier = "silver"
        elif score >= 50:
            action = "delayed_review"
            tier = "bronze"
        else:
            action = "pause"
            tier = "reject"

        df["data_quality_score"] = score

        report = DataQualityReport(
            record_count=n,
            data_quality_score=round(score, 2),
            anomalies=anomalies,
            action=action,
            tier=tier,
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
