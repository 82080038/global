"""AI Learning Engine (Fase 5).

Mengoptimasi factor weights secara dinamis berdasarkan:
1. Market regime (bull/bear/sideways) dari macro engine
2. Historical score performance — engine yang konsisten tinggi dapat bobot lebih
3. Data coverage — engine dengan data terbatas (e.g. fundamental .JK) diturunkan bobotnya
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trading_system.data.storage import DataStorage


def _get_default_weights():
    """Lazy import to avoid circular dependency."""
    from trading_system.decision.engine import DEFAULT_WEIGHTS
    return DEFAULT_WEIGHTS.copy()


# Regime-specific weight presets
# Keys match regimes from macro.py::classify_regime (easing, tightening, growth,
# slowdown, neutral, unknown) plus risk_off for TIP compatibility (§13.4 #6).
REGIME_WEIGHTS = {
    "easing": {
        "technical": 0.15,
        "fundamental": 0.30,
        "macro": 0.20,
        "global": 0.10,
        "relationship": 0.10,
        "sentiment": 0.15,
    },
    "tightening": {
        "technical": 0.25,
        "fundamental": 0.15,
        "macro": 0.25,
        "global": 0.15,
        "relationship": 0.10,
        "sentiment": 0.10,
    },
    "growth": {
        "technical": 0.20,
        "fundamental": 0.25,
        "macro": 0.15,
        "global": 0.15,
        "relationship": 0.10,
        "sentiment": 0.15,
    },
    "slowdown": {
        "technical": 0.25,
        "fundamental": 0.20,
        "macro": 0.25,
        "global": 0.15,
        "relationship": 0.10,
        "sentiment": 0.05,
    },
    "neutral": None,  # Will be set to DEFAULT_WEIGHTS at runtime
    "unknown": None,  # Will be set to DEFAULT_WEIGHTS at runtime
    "risk_off": {
        "technical": 0.10,
        "fundamental": 0.20,
        "macro": 0.25,
        "global": 0.20,
        "relationship": 0.15,
        "sentiment": 0.10,
    },
    "risk_on": {
        "technical": 0.15,
        "fundamental": 0.30,
        "macro": 0.20,
        "global": 0.10,
        "relationship": 0.10,
        "sentiment": 0.15,
    },
}


class AILearningEngine:
    name = "ai_learning"

    def __init__(self, storage: DataStorage | None = None):
        self.storage = storage or DataStorage()

    def get_factor_weights(self, ticker: str | None = None, regime: str | None = None) -> dict:
        """Get dynamically adjusted factor weights.

        Priority:
        1. AI-trained weights from DB (if fresh, <7 days old)
        2. Regime-based + consistency-adjusted weights
        3. DEFAULT_WEIGHTS
        """
        # Step 1: Check for AI-trained weights from DB
        ai_weights = self.storage.get_ai_weights(ticker=ticker, max_age_days=7)
        if ai_weights is not None:
            return ai_weights

        # Step 2: Base weights from regime
        if regime is None or regime == "neutral":
            base = _get_default_weights()
        else:
            base = REGIME_WEIGHTS.get(regime)
            if base is None:
                base = _get_default_weights()
            else:
                base = base.copy()

        if ticker is None:
            return base

        # Step 2: Load historical scores for this ticker
        df = self.storage.load_scores(ticker)
        if df.empty:
            return base

        # Step 3: Compute per-engine consistency and coverage
        adjustments = {}
        for engine in base:
            engine_scores = df[df["engine"] == engine]["score"]
            if engine_scores.empty:
                # No historical data — reduce weight slightly
                adjustments[engine] = 0.85
                continue

            # Consistency: low variance = more reliable
            std = float(engine_scores.std()) if len(engine_scores) > 1 else 0.0
            mean_score = float(engine_scores.mean())

            # High mean + low std = increase weight; low mean or high std = decrease
            if mean_score >= 60 and std < 15:
                adjustments[engine] = 1.15
            elif mean_score >= 50 and std < 20:
                adjustments[engine] = 1.05
            elif mean_score < 40 or std > 25:
                adjustments[engine] = 0.80
            else:
                adjustments[engine] = 1.0

        # Step 4: Check fundamental data coverage and weight_multiplier from breakdown
        fund_df = df[df["engine"] == "fundamental"]
        if not fund_df.empty:
            import json
            try:
                breakdown = json.loads(fund_df.iloc[0]["breakdown"])
                coverage = breakdown.get("_data_coverage", 1.0)
                weight_multiplier = breakdown.get("_weight_multiplier", 1.0)
                # If weight_multiplier is 0, fundamental data is unavailable — zero out weight
                if weight_multiplier == 0.0:
                    adjustments["fundamental"] = 0.0
                elif coverage < 0.6:
                    adjustments["fundamental"] *= 0.7
                elif coverage < 0.4:
                    adjustments["fundamental"] *= 0.5
            except Exception:
                pass

        # Step 5: Apply adjustments and renormalize
        adjusted = {k: base[k] * adjustments.get(k, 1.0) for k in base}
        total = sum(adjusted.values())
        if total > 0:
            adjusted = {k: round(v / total, 4) for k, v in adjusted.items()}

        return adjusted

    def feature_importance(self, scores: dict) -> list[dict]:
        total = sum(s for s in scores.values() if s is not None)
        if total == 0:
            return []
        return [
            {"factor": k, "importance": round(v / total, 4) if v is not None else 0}
            for k, v in scores.items()
        ]

    def get_regime(self, ticker: str | None = None) -> str:
        """Detect macro regime from stored macro scores."""
        if ticker is None:
            return "neutral"
        macro_df = self.storage.load_scores(ticker, engine="macro")
        if macro_df.empty:
            return "neutral"
        import json
        try:
            breakdown = json.loads(macro_df.iloc[0]["breakdown"])
            return breakdown.get("regime", "neutral")
        except Exception:
            return "neutral"

    def train_linear_regression(self, ticker: str | None = None) -> dict:
        """Train Linear Regression to optimize factor weights from historical data.

        For each day with scores, the target is the next-day return.
        The regression coefficients are normalized into weights.

        Returns dict with trained weights, r2_score, and n_samples.
        """
        from sklearn.linear_model import LinearRegression
        from sklearn.model_selection import TimeSeriesSplit
        from sklearn.preprocessing import StandardScaler

        # Gather tickers
        if ticker:
            tickers = [ticker]
        else:
            tickers = self.storage.list_active_equity_tickers()

        all_rows = []
        for t in tickers:
            scores_df = self.storage.load_scores(t)
            if scores_df.empty:
                continue
            price_df = self.storage.load_ohlcv(t)
            if price_df.empty:
                continue

            # Compute next-day returns
            # load_ohlcv sets timestamp as index — reset to column for processing
            price_df = price_df.reset_index()
            price_df = price_df.sort_values("timestamp")
            price_df["next_close"] = price_df["close"].shift(-1)
            price_df["forward_return"] = (price_df["next_close"] / price_df["close"] - 1)
            price_df["date"] = pd.to_datetime(price_df["timestamp"]).dt.date

            # Pivot scores: one row per date, columns = engine scores
            # scores table uses 'as_of' column (mixed ISO datetime formats with/without tz)
            scores_df["date"] = pd.to_datetime(scores_df["as_of"], utc=True, errors="coerce").dt.date
            scores_df = scores_df.dropna(subset=["date"])
            if scores_df.empty:
                continue
            pivot = scores_df.pivot_table(index="date", columns="engine", values="score", aggfunc="first")
            pivot = pivot.reset_index()

            # Merge with forward returns
            merged = pivot.merge(
                price_df[["date", "forward_return"]].dropna(subset=["forward_return"]),
                on="date",
                how="inner",
            )

            if not merged.empty:
                all_rows.append(merged)

        if not all_rows:
            return {"status": "no_data", "message": "No historical scores + returns to train on"}

        df = pd.concat(all_rows, ignore_index=True)

        # Feature columns = engine names from DEFAULT_WEIGHTS
        feature_cols = list(_get_default_weights().keys())
        X = df[feature_cols].fillna(0).values
        y = df["forward_return"].values

        # Rule of thumb >= 10-20 sampel per fitur (6 fitur) -> minimal 60-120 sampel.
        # Ambang lama (20) terlalu kecil dan menghasilkan bobot yang tidak stabil.
        min_samples = 60
        if len(X) < min_samples:
            return {"status": "insufficient_data", "message": f"Only {len(X)} samples, need >= {min_samples}"}

        # Standardize features
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # Fit regression on full data (untuk bobot final)
        reg = LinearRegression()
        reg.fit(X_scaled, y)
        r2_in_sample = reg.score(X_scaled, y)

        # Out-of-sample validation via TimeSeriesSplit — R^2 in-sample selalu
        # optimis dan tidak mencerminkan kemampuan generalisasi ke data baru.
        n_splits = min(5, len(X) // min_samples) or 1
        oos_r2_scores = []
        if n_splits >= 2:
            tscv = TimeSeriesSplit(n_splits=n_splits)
            for train_idx, test_idx in tscv.split(X_scaled):
                fold_reg = LinearRegression()
                fold_reg.fit(X_scaled[train_idx], y[train_idx])
                oos_r2_scores.append(fold_reg.score(X_scaled[test_idx], y[test_idx]))
        oos_r2 = float(np.mean(oos_r2_scores)) if oos_r2_scores else None

        # Non-negative constraint: faktor yang berkorelasi negatif dengan forward
        # return tidak boleh mendapat bobot positif (sebelumnya np.abs() membuang
        # arah/tanda koefisien, sehingga faktor yang justru merugikan performa
        # bisa mendapat bobot besar). Clip ke 0 alih-alih ambil nilai absolut.
        coefs = np.clip(reg.coef_, 0, None)
        total = coefs.sum()
        if total == 0:
            # Fallback to defaults if all coefs are non-positive
            weights = _get_default_weights()
        else:
            weights = {col: round(float(coefs[i] / total), 4) for i, col in enumerate(feature_cols)}

        # Ensure weights sum to 1
        weight_sum = sum(weights.values())
        if weight_sum > 0:
            weights = {k: round(v / weight_sum, 4) for k, v in weights.items()}

        # Save to DB
        self.storage.save_ai_weights(weights, ticker=ticker, r2_score=r2_in_sample, n_samples=len(X))

        return {
            "status": "ok",
            "weights": weights,
            "r2_score": round(float(r2_in_sample), 4),
            "oos_r2_score": round(oos_r2, 4) if oos_r2 is not None else None,
            "n_splits": n_splits if oos_r2_scores else 0,
            "n_samples": len(X),
            "ticker": ticker or "all",
        }

