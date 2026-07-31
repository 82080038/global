"""Advanced Technical Indicators (K, §4.1).

Extends TechnicalAnalysisEngine with:
- Ichimoku Cloud
- Williams %R
- On-Balance Volume (OBV)
- Stochastic RSI
- Multi-timeframe analysis
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ichimoku_cloud(df: pd.DataFrame) -> pd.DataFrame:
    """Compute Ichimoku Cloud indicators.

    Returns DataFrame with tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    nine_high = high.rolling(9).max()
    nine_low = low.rolling(9).min()
    tenkan_sen = (nine_high + nine_low) / 2

    period26_high = high.rolling(26).max()
    period26_low = low.rolling(26).min()
    kijun_sen = (period26_high + period26_low) / 2

    senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(26)
    period52_high = high.rolling(52).max()
    period52_low = low.rolling(52).min()
    senkou_span_b = ((period52_high + period52_low) / 2).shift(26)

    chikou_span = close.shift(-26)

    result = pd.DataFrame(index=df.index)
    result["tenkan_sen"] = tenkan_sen
    result["kijun_sen"] = kijun_sen
    result["senkou_span_a"] = senkou_span_a
    result["senkou_span_b"] = senkou_span_b
    result["chikou_span"] = chikou_span
    return result


def williams_r(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute Williams %R indicator.

    Range: -100 to 0. Below -80 = oversold, above -20 = overbought.
    """
    high = df["high"].rolling(period).max()
    low = df["low"].rolling(period).min()
    close = df["close"]
    wr = -100 * (high - close) / (high - low)
    wr = wr.replace([np.inf, -np.inf], -50)
    return wr.fillna(-50)


def on_balance_volume(df: pd.DataFrame) -> pd.Series:
    """Compute On-Balance Volume (OBV)."""
    close = df["close"]
    volume = df["volume"]
    direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    obv = (direction * volume).cumsum()
    return obv


def stochastic_rsi(df: pd.DataFrame, rsi_period: int = 14, stoch_period: int = 14) -> pd.Series:
    """Compute Stochastic RSI.

    Range: 0 to 1. Below 0.2 = oversold, above 0.8 = overbought.
    """
    close = df["close"]
    delta = close.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(rsi_period).mean()
    avg_loss = loss.rolling(rsi_period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.fillna(50)

    rsi_min = rsi.rolling(stoch_period).min()
    rsi_max = rsi.rolling(stoch_period).max()
    stoch_rsi = (rsi - rsi_min) / (rsi_max - rsi_min).replace(0, np.nan)
    return stoch_rsi.fillna(0.5).clip(0, 1)


def compute_advanced_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all advanced technical indicators and return merged DataFrame.

    Adds: ichimoku (5 cols), williams_r, obv, stochastic_rsi
    """
    result = df.copy()
    ich = ichimoku_cloud(df)
    for col in ich.columns:
        result[f"ichimoku_{col}"] = ich[col]
    result["williams_r"] = williams_r(df)
    result["obv"] = on_balance_volume(df)
    result["stoch_rsi"] = stochastic_rsi(df)
    return result
