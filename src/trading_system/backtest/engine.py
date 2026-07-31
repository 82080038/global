"""Backtesting Engine (Phase 1).

Cost model via consolidated risk/costs.py (P2-4):
- buy fee: 0.15%
- sell fee: 0.25% (broker 0.15% + PPh 0.1%)
- levy: 0.00043%
- slippage: 0.05%
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from trading_system.backtest.metrics import compute_metrics
from trading_system.config import (
    DEFAULT_BENCHMARK,
    IDX_LOT_SIZE,
    TRADING_CAPITAL,
    round_to_tick,
)
from trading_system.data.storage import DataStorage
from trading_system.risk.costs import CostModel


class BacktestEngine:
    def __init__(self, storage: DataStorage | None = None, cost_model: CostModel | None = None):
        self.storage = storage or DataStorage()
        self.default_cost_model = cost_model or CostModel()

    def run(
        self,
        ticker: str,
        strategy,
        start: str | None = None,
        end: str | None = None,
        initial_capital: float = TRADING_CAPITAL,
        cost_model: CostModel | None = None,
    ) -> dict[str, Any]:
        """Jalankan backtest event-driven sederhana."""
        df = self.storage.load_ohlcv(ticker, start=start, end=end)
        if df.empty:
            return {"status": "error", "message": f"No data for {ticker}"}

        cost = cost_model or CostModel()
        result = self._run_core(df, strategy, initial_capital, cost, ticker=ticker)

        if result["status"] != "ok":
            return result

        # Benchmark
        bm = self.storage.load_ohlcv(DEFAULT_BENCHMARK, start=start, end=end)
        if not bm.empty:
            bm_equity = (1 + bm["close"].pct_change().fillna(0)).cumprod()
        else:
            bm_equity = pd.Series()

        equity = result.pop("equity_curve")
        trade_df = result.pop("trade_history")
        result["metrics"] = compute_metrics(trade_df, equity, bm_equity)
        result["equity_curve"] = equity
        result["trade_history"] = trade_df
        return result

    def run_with_data(
        self,
        df: pd.DataFrame,
        strategy,
        initial_capital: float = TRADING_CAPITAL,
        cost_model: CostModel | None = None,
    ) -> dict[str, Any]:
        """Run backtest on a pre-loaded DataFrame (for walk-forward analysis)."""
        cost = cost_model or self.default_cost_model or CostModel()
        result = self._run_core(df, strategy, initial_capital, cost, ticker="OOS")

        if result["status"] != "ok":
            return result

        equity = result.pop("equity_curve")
        trade_df = result.pop("trade_history")
        result["metrics"] = compute_metrics(trade_df, equity)
        result["equity_curve"] = equity
        result["trade_history"] = trade_df
        return result

    def _run_core(
        self,
        df: pd.DataFrame,
        strategy,
        initial_capital: float,
        cost: CostModel,
        ticker: str = "OOS",
    ) -> dict[str, Any]:
        """Core backtest loop — next-bar-open execution, lot 100, tick size IDX.

        Signal generated at bar t is executed at the **open** of bar t+1 to
        eliminate look-ahead bias (§3.1 SARAN_PENGEMBANGAN.md). Share counts
        are rounded to IDX lot size (100) and fill prices to IDX tick size.
        """
        if df.empty:
            return {"status": "error", "message": "Empty DataFrame"}

        df = strategy.generate_signals(df)
        if "signal" not in df.columns:
            return {"status": "error", "message": "Strategy did not generate 'signal' column"}

        # Point-in-time: skip warmup period to avoid look-ahead bias
        warmup = getattr(strategy, "warmup_periods", 0)
        if warmup > 0 and len(df) > warmup:
            df.loc[df.index[:warmup], "signal"] = 0

        # Pre-compute next-bar open for execution (shift -1)
        df["next_open"] = df["open"].shift(-1) if "open" in df.columns else df["close"].shift(-1)

        capital = initial_capital
        position = 0
        equity_curve = []
        trade_history = []
        entry_price = 0.0
        entry_time = None

        rows = list(df.iterrows())
        for i, (idx, row) in enumerate(rows):
            price = row["close"]
            equity = capital + position * price
            equity_curve.append((idx, equity))

            sig = row.get("signal", 0)
            # Execution happens at next bar's open (look-ahead bias fix)
            next_open = row.get("next_open")
            if next_open is None or pd.isna(next_open):
                continue  # last bar — no next bar to execute at

            if sig == 1 and position == 0:
                raw_fill = next_open * (1 + cost.buy_cost_pct())
                fill_price = round_to_tick(raw_fill)
                # Round down to nearest lot
                lots = int((capital * 0.99) // (fill_price * IDX_LOT_SIZE))
                shares = lots * IDX_LOT_SIZE
                if shares > 0:
                    cost_value = shares * fill_price
                    capital -= cost_value
                    position = shares
                    entry_price = fill_price
                    entry_time = str(idx)
                    self.storage.audit(
                        "backtest.trade",
                        {
                            "timestamp": str(idx),
                            "ticker": ticker,
                            "action": "BUY",
                            "price": fill_price,
                            "shares": int(shares),
                            "capital_remaining": float(capital),
                        },
                    )
            elif sig == -1 and position > 0:
                raw_fill = next_open * (1 - cost.sell_cost_pct())
                fill_price = round_to_tick(raw_fill)
                proceeds = position * fill_price
                pnl = proceeds - (position * entry_price)
                capital += proceeds
                trade_history.append({
                    "ticker": ticker,
                    "entry_time": entry_time,
                    "exit_time": str(idx),
                    "entry_price": float(entry_price),
                    "exit_price": float(fill_price),
                    "shares": int(position),
                    "pnl": float(pnl),
                    "fees_pct": float(cost.sell_cost_pct()),
                })
                sold_shares = position
                position = 0
                self.storage.audit(
                    "backtest.trade",
                    {
                        "timestamp": str(idx),
                        "ticker": ticker,
                        "action": "SELL",
                        "price": fill_price,
                        "shares": int(sold_shares),
                        "pnl": float(pnl),
                    },
                )

        # Force close at end if still in position (at last close)
        if position > 0:
            last = df.iloc[-1]
            raw_fill = last["close"] * (1 - cost.sell_cost_pct())
            fill_price = round_to_tick(raw_fill)
            proceeds = position * fill_price
            pnl = proceeds - (position * entry_price)
            capital += proceeds
            trade_history.append({
                "ticker": ticker,
                "entry_time": entry_time,
                "exit_time": str(df.index[-1]),
                "entry_price": float(entry_price),
                "exit_price": float(fill_price),
                "shares": int(position),
                "pnl": float(pnl),
                "fees_pct": float(cost.sell_cost_pct()),
            })
            position = 0

        equity = pd.DataFrame(equity_curve, columns=["timestamp", "equity"]).set_index("timestamp")["equity"]
        trade_df = pd.DataFrame(trade_history)

        return {
            "status": "ok",
            "ticker": ticker,
            "strategy": strategy.name,
            "initial_capital": initial_capital,
            "final_equity": round(equity.iloc[-1], 2),
            "equity_curve": equity,
            "trade_history": trade_df,
        }
