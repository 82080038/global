"""Risk Engine (Fase 4).

Menghitung ukuran posisi, stop loss, take profit, VaR (Value at Risk),
Max Drawdown harian, dan risk flags berdasarkan volatilitas & likuiditas.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from trading_system.config import TRADING_CAPITAL
from trading_system.data.storage import DataStorage
from trading_system.risk.costs import compute_atr, get_default_cost_model


class RiskEngine:
    name = "risk"

    def __init__(self, storage: DataStorage | None = None):
        self.storage = storage or DataStorage()

    def analyze(self, ticker: str, capital: float = TRADING_CAPITAL, risk_per_trade: float = 0.01) -> dict:
        df = self.storage.load_ohlcv(ticker)
        if df.empty:
            return {"status": "error", "message": f"No OHLCV for {ticker}"}

        close = df["close"]
        volume = df["volume"]

        last_price = float(close.iloc[-1])
        atr = self._atr(df, 14)
        avg_volume_raw = float(volume.rolling(20).mean().iloc[-1]) if len(volume) >= 20 else float(volume.mean()) if not volume.empty else 0
        avg_volume = avg_volume_raw if not pd.isna(avg_volume_raw) else 0
        volatility_raw = float(close.pct_change().rolling(20).std().iloc[-1] * np.sqrt(252)) if len(close) >= 20 else 0.2
        volatility = volatility_raw if not pd.isna(volatility_raw) else 0.2

        # Position sizing: target risk 1% of capital, stop = 1.5 ATR
        stop_distance = 1.5 * atr if not pd.isna(atr) and atr > 0 else last_price * 0.05
        stop_loss = last_price - stop_distance
        take_profit = last_price + 2 * stop_distance

        # Fixed fraction position size
        risk_amount = capital * risk_per_trade
        position_value = risk_amount / (stop_distance / last_price)
        position_size = min(position_value / capital, 0.1)  # max 10% of capital

        # Liquidity: target position must be < 1% of avg daily volume value
        adv_value = avg_volume * last_price
        target_value = position_size * capital
        cost_model = get_default_cost_model()
        slippage = cost_model.estimate_slippage(target_value, adv_value)
        if adv_value > 0 and target_value > adv_value * 0.01:
            flags = ["LIQUIDITY_LOW"]
        else:
            flags = []

        if volatility > 0.5:
            flags.append("HIGH_VOLATILITY")

        # VaR (Value at Risk) — 95% and 99% confidence, 1-day horizon
        daily_returns = close.pct_change().dropna()
        var_95, var_99 = self._compute_var(daily_returns, last_price)
        cvar_95 = self._compute_cvar(daily_returns, 0.05)
        # Historical VaR (empirical percentile) — pembanding VaR parametrik yang
        # mengasumsikan distribusi normal (underestimate untuk return fat-tailed IDX).
        hist_var_95, hist_var_99 = self._compute_historical_var(daily_returns, last_price)

        # Max Drawdown (rolling 252-day window)
        max_drawdown = self._compute_max_drawdown(close)

        # Daily Max Drawdown (worst single-day decline)
        daily_max_loss = float(daily_returns.min()) if not daily_returns.empty else 0.0

        if max_drawdown < -0.25:
            flags.append("SEVERE_DRAWDOWN")

        return {
            "status": "ok",
            "engine": self.name,
            "ticker": ticker,
            "last_price": round(last_price, 2),
            "atr": round(atr, 4) if not pd.isna(atr) else None,
            "position_size": round(position_size, 4),
            "stop_loss": round(stop_loss, 2),
            "take_profit": round(take_profit, 2),
            "slippage": round(slippage, 4),
            "risk_flags": flags,
            "avg_daily_volume": round(avg_volume, 0),
            "var_95_1d": round(var_95, 2),
            "var_99_1d": round(var_99, 2),
            "historical_var_95_1d": round(hist_var_95, 2),
            "historical_var_99_1d": round(hist_var_99, 2),
            "cvar_95_1d": round(cvar_95, 2),
            "max_drawdown": round(max_drawdown, 4),
            "daily_max_loss": round(daily_max_loss, 4),
            "annualized_volatility": round(volatility, 4),
        }

    def _compute_var(self, returns: pd.Series, last_price: float, confidence_levels: tuple = (0.95, 0.99)) -> tuple:
        """Compute parametric VaR at 95% and 99% confidence (1-day horizon)."""
        if returns.empty or len(returns) < 20:
            return 0.0, 0.0
        mean = returns.mean()
        std = returns.std()
        var_95 = last_price * (mean - sp_stats.norm.ppf(0.95) * std)
        var_99 = last_price * (mean - sp_stats.norm.ppf(0.99) * std)
        # VaR is expressed as a positive loss amount
        return abs(var_95), abs(var_99)

    def _compute_historical_var(self, returns: pd.Series, last_price: float, confidence_levels: tuple = (0.95, 0.99)) -> tuple:
        """Compute historical (empirical percentile) VaR — tidak mengasumsikan
        distribusi normal, sehingga lebih robust terhadap fat-tail return saham IDX.
        """
        if returns.empty or len(returns) < 20:
            return 0.0, 0.0
        p95 = np.percentile(returns, (1 - confidence_levels[0]) * 100)
        p99 = np.percentile(returns, (1 - confidence_levels[1]) * 100)
        var_95 = last_price * abs(min(p95, 0.0))
        var_99 = last_price * abs(min(p99, 0.0))
        return abs(var_95), abs(var_99)

    def _compute_cvar(self, returns: pd.Series, alpha: float = 0.05) -> float:
        """Compute Conditional VaR (Expected Shortfall) at 95% confidence."""
        if returns.empty or len(returns) < 20:
            return 0.0
        var_threshold = returns.quantile(alpha)
        tail = returns[returns <= var_threshold]
        if tail.empty:
            return 0.0
        return abs(float(tail.mean()))

    def _compute_max_drawdown(self, close: pd.Series, window: int = 252) -> float:
        """Compute rolling max drawdown over a window."""
        if close.empty or len(close) < 2:
            return 0.0
        rolling_max = close.rolling(window, min_periods=1).max()
        drawdown = (close - rolling_max) / rolling_max
        return float(drawdown.min())

    def _atr(self, df: pd.DataFrame, window: int = 14) -> float:
        """ATR via consolidated costs.py (P2-4)."""
        atr_series = compute_atr(df, window)
        return float(atr_series.iloc[-1]) if not atr_series.empty else np.nan

    def calculate_portfolio_var(self, confidence: float = 0.95) -> dict:
        """Calculate portfolio-level VaR and CVaR from all open positions.

        Uses historical returns weighted by position value.
        """
        positions = self.storage.get_all_open_positions()
        if not positions:
            return {
                "status": "ok",
                "var_95": 0.0, "var_99": 0.0,
                "cvar_95": 0.0, "cvar_99": 0.0,
                "max_drawdown": 0.0,
                "annualized_volatility": 0.0,
                "portfolio_value": 0.0,
            }

        # Build weighted return series from all positions
        all_returns = []
        weights = []
        total_value = 0.0

        for pos in positions:
            ticker = pos["ticker"]
            qty = float(pos["quantity"])
            df = self.storage.load_ohlcv(ticker, limit=252)
            if df.empty or len(df) < 20:
                continue
            price = float(df["close"].iloc[-1])
            value = qty * price
            total_value += value
            returns = df["close"].pct_change().dropna()
            all_returns.append(returns)
            weights.append(value)

        if not all_returns or total_value == 0:
            return {
                "status": "ok",
                "var_95": 0.0, "var_99": 0.0,
                "cvar_95": 0.0, "cvar_99": 0.0,
                "max_drawdown": 0.0,
                "annualized_volatility": 0.0,
                "portfolio_value": 0.0,
            }

        # Normalize weights
        weights = np.array(weights) / sum(weights)

        # Align all return series and compute weighted portfolio returns
        max_len = max(len(r) for r in all_returns)
        portfolio_returns = pd.Series(np.zeros(max_len))
        for ret, w in zip(all_returns, weights):
            padded = ret.reindex(range(max_len - len(ret), max_len)).fillna(0).values
            portfolio_returns += padded * w

        portfolio_returns = portfolio_returns.dropna()

        # VaR (historical method)
        var_95 = abs(float(np.percentile(portfolio_returns, 5)))
        var_99 = abs(float(np.percentile(portfolio_returns, 1)))

        # CVaR (Expected Shortfall)
        cvar_95_threshold = np.percentile(portfolio_returns, 5)
        cvar_99_threshold = np.percentile(portfolio_returns, 1)
        cvar_95 = abs(float(portfolio_returns[portfolio_returns <= cvar_95_threshold].mean())) if (portfolio_returns <= cvar_95_threshold).any() else 0.0
        cvar_99 = abs(float(portfolio_returns[portfolio_returns <= cvar_99_threshold].mean())) if (portfolio_returns <= cvar_99_threshold).any() else 0.0

        # Max drawdown
        cumulative = (1 + portfolio_returns).cumprod()
        rolling_max = cumulative.cummax()
        drawdown = (cumulative - rolling_max) / rolling_max
        max_drawdown = abs(float(drawdown.min())) if not drawdown.empty else 0.0

        # Annualized volatility
        ann_vol = float(portfolio_returns.std() * np.sqrt(252)) if len(portfolio_returns) > 1 else 0.0

        return {
            "status": "ok",
            "var_95": round(var_95, 4),
            "var_99": round(var_99, 4),
            "cvar_95": round(cvar_95, 4),
            "cvar_99": round(cvar_99, 4),
            "max_drawdown": round(max_drawdown, 4),
            "annualized_volatility": round(ann_vol, 4),
            "portfolio_value": round(total_value, 2),
        }

    def save_daily_risk(self) -> dict:
        """Calculate and save daily portfolio risk metrics to DB."""
        metrics = self.calculate_portfolio_var()
        if metrics.get("status") != "ok":
            return metrics

        self.storage.save_daily_risk_metrics(
            var_95=metrics["var_95"],
            var_99=metrics["var_99"],
            cvar_95=metrics["cvar_95"],
            cvar_99=metrics["cvar_99"],
            max_drawdown=metrics["max_drawdown"],
            annualized_volatility=metrics["annualized_volatility"],
            portfolio_value=metrics["portfolio_value"],
        )
        return metrics
