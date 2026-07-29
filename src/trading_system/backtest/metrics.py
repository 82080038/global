"""Metrik kinerja backtest."""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_metrics(trade_history: pd.DataFrame, equity_curve: pd.Series, benchmark: pd.Series | None = None) -> dict:
    """Menghitung metrik backtest lengkap."""
    if equity_curve.empty:
        return {}

    returns = equity_curve.pct_change().dropna()
    if returns.empty:
        return {}

    # Total & CAGR
    total_return = equity_curve.iloc[-1] / equity_curve.iloc[0] - 1
    n_days = len(equity_curve)
    years = max(n_days / 252, 1e-6)
    cagr = (equity_curve.iloc[-1] / equity_curve.iloc[0]) ** (1 / years) - 1

    # Drawdown
    rolling_max = equity_curve.cummax()
    drawdown = (equity_curve - rolling_max) / rolling_max
    max_drawdown = drawdown.min()

    # Volatility & Ratios
    ann_volatility = returns.std() * np.sqrt(252)
    risk_free = 0.05 / 252  # asumsi 5% per tahun harian
    excess = returns - risk_free
    sharpe = excess.mean() / returns.std() * np.sqrt(252) if returns.std() != 0 else 0

    downside = returns[returns < 0]
    sortino = excess.mean() / (downside.std() * np.sqrt(252)) if not downside.empty and downside.std() != 0 else 0
    calmar = cagr / abs(max_drawdown) if max_drawdown != 0 else 0

    # Trade metrics
    if trade_history.empty:
        win_rate = 0
        profit_factor = 0
        avg_win = 0
        avg_loss = 0
        expectancy = 0
        n_trades = 0
    else:
        wins = trade_history[trade_history["pnl"] > 0]["pnl"]
        losses = trade_history[trade_history["pnl"] <= 0]["pnl"]
        n_trades = len(trade_history)
        win_rate = len(wins) / n_trades if n_trades else 0
        profit_factor = wins.sum() / abs(losses.sum()) if not losses.empty and losses.sum() != 0 else float("inf")
        avg_win = wins.mean() if not wins.empty else 0
        avg_loss = losses.mean() if not losses.empty else 0
        expectancy = trade_history["pnl"].mean() if n_trades else 0

    # Beta / Alpha
    if benchmark is not None and not benchmark.empty:
        bm_returns = benchmark.pct_change().dropna()
        common = returns.index.intersection(bm_returns.index)
        if len(common) > 1:
            cov = returns.loc[common].cov(bm_returns.loc[common])
            var = bm_returns.loc[common].var()
            beta = cov / var if var != 0 else 0
            alpha = (returns.loc[common].mean() - risk_free) - beta * (bm_returns.loc[common].mean() - risk_free)
        else:
            beta = np.nan
            alpha = np.nan
    else:
        beta = np.nan
        alpha = np.nan

    return {
        "total_return": round(total_return, 4),
        "cagr": round(cagr, 4),
        "max_drawdown": round(max_drawdown, 4),
        "sharpe_ratio": round(sharpe, 4),
        "sortino_ratio": round(sortino, 4),
        "calmar_ratio": round(calmar, 4),
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 4) if not np.isinf(profit_factor) else None,
        "average_win": round(avg_win, 4),
        "average_loss": round(avg_loss, 4),
        "expectancy": round(expectancy, 4),
        "volatility": round(ann_volatility, 4),
        "beta": round(beta, 4) if not np.isnan(beta) else None,
        "alpha": round(alpha, 4) if not np.isnan(alpha) else None,
        "number_of_trades": n_trades,
        "exposure_time": round(n_days / 252, 4),
    }
