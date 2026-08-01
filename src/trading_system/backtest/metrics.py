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
    start_equity = equity_curve.iloc[0]
    end_equity = equity_curve.iloc[-1]
    if start_equity == 0:
        # Avoid division by zero / inf when the curve starts at zero capital.
        total_return = 0.0
        cagr = 0.0
    else:
        total_return = end_equity / start_equity - 1
        n_days = len(equity_curve)
        years = max(n_days / 252, 1e-6)
        cagr = (end_equity / start_equity) ** (1 / years) - 1

    # Drawdown
    rolling_max = equity_curve.cummax()
    # Guard against rolling_max == 0 (all-zero equity) producing inf.
    drawdown = (equity_curve - rolling_max) / rolling_max.replace(0, pd.NA)
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


def monte_carlo_simulation(
    returns: pd.Series,
    n_simulations: int = 1000,
    n_periods: int = 252,
    initial_capital: float = 100_000_000,
    confidence_levels: tuple = (0.05, 0.50, 0.95),
    block_size: int | None = None,
) -> dict:
    """Run Monte Carlo simulation by resampling historical returns.

    Generates n_simulations random return sequences (bootstrap) and computes
    the distribution of final equity, max drawdown, and Sharpe ratio.

    When ``block_size`` is set, uses **block bootstrap** to preserve
    autocorrelation and volatility clustering present in the original
    series (§3.6 SARAN_PENGEMBANGAN.md).  When ``None``, falls back to
    IID bootstrap.

    Args:
        returns: Daily returns series from backtest.
        n_simulations: Number of simulated paths.
        n_periods: Length of each simulated path (default 252 = 1 year).
        initial_capital: Starting capital for each simulation.
        confidence_levels: Percentiles to report (0-1 scale).
        block_size: Block length for block bootstrap (None = IID).

    Returns:
        Dict with percentile bands for final_equity, max_drawdown, sharpe_ratio.
    """
    if returns.empty or len(returns) < 20:
        return {"status": "insufficient_data"}

    rng = np.random.default_rng(seed=42)
    returns_arr = returns.values
    n = len(returns_arr)

    # Validate block_size
    if block_size is not None and block_size < 1:
        block_size = None

    final_equities = np.zeros(n_simulations)
    max_drawdowns = np.zeros(n_simulations)
    sharpe_ratios = np.zeros(n_simulations)

    for i in range(n_simulations):
        if block_size is not None and block_size < n:
            # Block bootstrap: resample in contiguous blocks
            sampled = np.empty(n_periods)
            filled = 0
            while filled < n_periods:
                start = rng.integers(0, n - block_size + 1)
                block = returns_arr[start:start + block_size]
                take = min(block_size, n_periods - filled)
                sampled[filled:filled + take] = block[:take]
                filled += take
        else:
            # IID bootstrap
            sampled = rng.choice(returns_arr, size=n_periods, replace=True)
        equity = initial_capital * np.cumprod(1 + sampled)

        final_equities[i] = equity[-1]

        # Max drawdown for this path
        rolling_max = np.maximum.accumulate(equity)
        drawdowns = (equity - rolling_max) / rolling_max
        max_drawdowns[i] = drawdowns.min()

        # Sharpe ratio for this path
        if sampled.std() > 0:
            sharpe_ratios[i] = sampled.mean() / sampled.std() * np.sqrt(252)
        else:
            sharpe_ratios[i] = 0.0

    # Compute percentile bands
    def pct(arr, p):
        return float(np.percentile(arr, p * 100))

    result = {
        "n_simulations": n_simulations,
        "n_periods": n_periods,
        "initial_capital": initial_capital,
        "block_size": block_size,
        "final_equity": {
            f"p{int(p*100)}": round(pct(final_equities, p), 2)
            for p in confidence_levels
        },
        "max_drawdown": {
            f"p{int(p*100)}": round(pct(max_drawdowns, p), 4)
            for p in confidence_levels
        },
        "sharpe_ratio": {
            f"p{int(p*100)}": round(pct(sharpe_ratios, p), 4)
            for p in confidence_levels
        },
        "mean_final_equity": round(float(np.mean(final_equities)), 2),
        "median_final_equity": round(float(np.median(final_equities)), 2),
        "prob_profit": round(float(np.mean(final_equities > initial_capital)), 4),
        "prob_loss_20pct": round(float(np.mean(final_equities < initial_capital * 0.8)), 4),
        "worst_drawdown": round(float(max_drawdowns.min()), 4),
        "best_drawdown": round(float(max_drawdowns.max()), 4),
    }

    return result


def walk_forward_analysis(
    df: pd.DataFrame,
    strategy_factory,
    n_splits: int = 5,
    train_size: int = 252,
    test_size: int = 63,
    cost_model=None,
) -> dict:
    """Run walk-forward (in-sample/out-of-sample) analysis.

    Splits data into n_splits segments, each with train_size training period
    and test_size out-of-sample test period. Reports OOS performance consistency.

    Args:
        df: OHLCV DataFrame with timestamp index.
        strategy_factory: Callable that returns a fresh strategy instance.
        n_splits: Number of walk-forward windows.
        train_size: Training window length (bars).
        test_size: Out-of-sample test window length (bars).
        cost_model: Optional CostModel for realistic returns.

    Returns:
        Dict with per-split OOS metrics and aggregate consistency scores.
    """
    from trading_system.backtest.engine import BacktestEngine, CostModel

    if df.empty or len(df) < train_size + test_size:
        return {"status": "insufficient_data"}

    engine = BacktestEngine(cost_model=cost_model or CostModel())
    splits = []
    total_len = len(df)

    for i in range(n_splits):
        start = i * test_size
        train_end = start + train_size
        test_end = train_end + test_size

        if test_end > total_len:
            break

        train_df = df.iloc[start:train_end]
        test_df = df.iloc[train_end:test_end]

        if test_df.empty:
            break

        # Run strategy on OOS data
        strategy = strategy_factory()
        result = engine.run_with_data(test_df, strategy)

        if result.get("status") == "ok":
            metrics = result.get("metrics", {})
            splits.append({
                "split": i + 1,
                "train_period": f"{train_df.index[0].date()} → {train_df.index[-1].date()}",
                "test_period": f"{test_df.index[0].date()} → {test_df.index[-1].date()}",
                "oos_return": metrics.get("total_return", 0),
                "oos_sharpe": metrics.get("sharpe_ratio", 0),
                "oos_max_drawdown": metrics.get("max_drawdown", 0),
                "oos_win_rate": metrics.get("win_rate", 0),
            })

    if not splits:
        return {"status": "no_valid_splits"}

    # Aggregate consistency
    oos_returns = [s["oos_return"] for s in splits]
    oos_sharpes = [s["oos_sharpe"] for s in splits]

    return {
        "n_splits": len(splits),
        "splits": splits,
        "oos_mean_return": round(float(np.mean(oos_returns)), 4),
        "oos_std_return": round(float(np.std(oos_returns)), 4),
        "oos_mean_sharpe": round(float(np.mean(oos_sharpes)), 4),
        "oos_positive_splits": int(sum(1 for r in oos_returns if r > 0)),
        "oos_consistency": round(float(np.mean([1 if r > 0 else 0 for r in oos_returns])), 4),
    }
