"""Stock screener — adaptasi dari pasar_modal/src/trading/screener.py.

Screener berbasis teknikal dengan template technical, momentum, dan value.
Bekerja dengan DataFrame yang sudah memiliki kolom indikator teknikal.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pandas as pd

ScreenRule = Callable[[pd.DataFrame], pd.Series]


def _latest(features_df: pd.DataFrame) -> pd.DataFrame:
    """Return the latest row per ticker from a feature DataFrame."""
    if "ticker" not in features_df.columns:
        return features_df.tail(1).copy()
    return features_df.sort_values("date" if "date" in features_df.columns else features_df.columns[0]).groupby("ticker").tail(1).copy()


def technical_template(
    features_df: pd.DataFrame,
    min_rsi: float = 30.0,
    max_rsi: float = 70.0,
    min_adx: float = 20.0,
    min_volume_ratio: float = 1.0,
) -> pd.DataFrame:
    """Screen stocks based on technical criteria.

    Rules:
        - Price above SMA 50 (trending)
        - RSI between min_rsi and max_rsi
        - ADX above min_adx (trend strength)
        - Volume above 20-day average
        - Close above lower Bollinger Band
    """
    latest = _latest(features_df)
    required = ["close", "sma_50", "rsi_14", "adx_14", "volume", "volume_sma_20", "bb_lower"]
    missing = [c for c in required if c not in latest.columns]
    if missing:
        return pd.DataFrame()

    mask = (
        (latest["close"] > latest["sma_50"])
        & (latest["rsi_14"] >= min_rsi)
        & (latest["rsi_14"] <= max_rsi)
        & (latest["adx_14"] >= min_adx)
        & (latest["volume"] >= latest["volume_sma_20"] * min_volume_ratio)
        & (latest["close"] > latest["bb_lower"])
    )

    result = latest[mask].copy()
    result["score"] = (
        result["rsi_14"].clip(upper=50) + result["adx_14"]
    )
    if "close_above_sma50" in result.columns:
        result["score"] = result["score"] + result["close_above_sma50"] * 10
    return result


def momentum_template(features_df: pd.DataFrame) -> pd.DataFrame:
    """Screen momentum stocks.

    Rules:
        - Close above SMA 50 and SMA 200
        - RSI > 50 but not overbought
        - ADX > 25
        - MACD histogram positive
    """
    latest = _latest(features_df)
    required = ["close", "sma_50", "sma_200", "rsi_14", "adx_14", "macd_hist"]
    missing = [c for c in required if c not in latest.columns]
    if missing:
        return pd.DataFrame()

    mask = (
        (latest["close"] > latest["sma_50"])
        & (latest["close"] > latest["sma_200"])
        & (latest["rsi_14"] > 50)
        & (latest["rsi_14"] < 75)
        & (latest["adx_14"] > 25)
        & (latest["macd_hist"] > 0)
    )

    result = latest[mask].copy()
    result["score"] = result["macd_hist"] + result["rsi_14"] + result["adx_14"]
    return result


def value_template(
    features_df: pd.DataFrame,
    max_per: float = 15.0,
    min_roe: float = 10.0,
    max_der: float = 1.0,
) -> pd.DataFrame:
    """Value screening based on fundamentals.

    Requires columns: per, roe, der in the features DataFrame.
    Returns empty if fundamental columns not available.
    """
    latest = _latest(features_df)
    required = ["per", "roe", "der"]
    missing = [c for c in required if c not in latest.columns]
    if missing:
        return pd.DataFrame()

    mask = (
        (latest["per"] <= max_per)
        & (latest["per"] > 0)
        & (latest["roe"] >= min_roe)
        & (latest["der"] <= max_der)
    )

    result = latest[mask].copy()
    result["score"] = (latest["roe"] / latest["per"].clip(lower=1)).fillna(0)
    return result


TEMPLATES: dict[str, Callable[[pd.DataFrame], pd.DataFrame]] = {
    "technical": technical_template,
    "momentum": momentum_template,
    "value": value_template,
}


def screen_universe(
    features_df: pd.DataFrame,
    template: str = "technical",
    as_of: date | None = None,
) -> pd.DataFrame:
    """Run a screening template on a universe of tickers.

    Args:
        features_df: DataFrame with technical indicator columns.
        template: Name of screening template ('technical', 'momentum', 'value').
        as_of: Optional date to screen as-of.

    Returns:
        DataFrame of passing stocks with scores and ranks.
    """
    if template not in TEMPLATES:
        raise ValueError(f"Unknown template: {template}. Available: {list(TEMPLATES.keys())}")

    if features_df.empty:
        return pd.DataFrame()

    if as_of is not None and "date" in features_df.columns:
        features_df = features_df[features_df["date"] <= pd.Timestamp(as_of)]

    result = TEMPLATES[template](features_df)
    if result.empty:
        return result

    result = result.sort_values("score", ascending=False).reset_index(drop=True)
    result["rank"] = result.index + 1

    return result
