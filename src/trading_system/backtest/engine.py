"""Backtesting Engine (Phase 1).

Cost model sederhana:
- buy fee: 0.15%
- sell fee: 0.25% (broker 0.15% + PPh 0.1%)
- levy: 0.00043%
- slippage: 0.05%
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from trading_system.config import (
    DEFAULT_BENCHMARK,
    DEFAULT_BROKER_FEE_BUY,
    DEFAULT_BROKER_FEE_SELL,
    DEFAULT_LEVY,
    DEFAULT_SLIPPAGE,
)
from trading_system.backtest.metrics import compute_metrics
from trading_system.backtest.strategies import BuyAndHold, MovingAverageCrossover
from trading_system.data.storage import DataStorage


class CostModel:
    def __init__(
        self,
        buy_fee: float = DEFAULT_BROKER_FEE_BUY,
        sell_fee: float = DEFAULT_BROKER_FEE_SELL,
        levy: float = DEFAULT_LEVY,
        slippage: float = DEFAULT_SLIPPAGE,
    ):
        self.buy_fee = buy_fee
        self.sell_fee = sell_fee
        self.levy = levy
        self.slippage = slippage

    def buy_cost_pct(self) -> float:
        return self.buy_fee + self.levy + self.slippage

    def sell_cost_pct(self) -> float:
        return self.sell_fee + self.levy + self.slippage


class BacktestEngine:
    def __init__(self, storage: DataStorage | None = None):
        self.storage = storage or DataStorage()

    def run(
        self,
        ticker: str,
        strategy,
        start: str | None = None,
        end: str | None = None,
        initial_capital: float = 1_000_000_000,
        cost_model: CostModel | None = None,
    ) -> dict[str, Any]:
        """Jalankan backtest event-driven sederhana."""
        cost = cost_model or CostModel()

        df = self.storage.load_ohlcv(ticker, start=start, end=end)
        if df.empty:
            return {"status": "error", "message": f"No data for {ticker}"}

        df = strategy.generate_signals(df)
        if "signal" not in df.columns:
            return {"status": "error", "message": "Strategy did not generate 'signal' column"}

        capital = initial_capital
        position = 0
        equity_curve = []
        trade_history = []
        entry_price = 0
        entry_time = None

        for idx, row in df.iterrows():
            price = row["close"]
            equity = capital + position * price
            equity_curve.append((idx, equity))

            sig = row.get("signal", 0)
            if sig == 1 and position == 0:
                # Buy at close + slippage
                fill_price = price * (1 + cost.buy_cost_pct())
                shares = (capital * 0.99) // fill_price  # gunakan 99% capital, biarkan cash kecil
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
                fill_price = price * (1 - cost.sell_cost_pct())
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

        # Force close at end if still in position
        if position > 0:
            last = df.iloc[-1]
            fill_price = last["close"] * (1 - cost.sell_cost_pct())
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

        # Benchmark
        bm = self.storage.load_ohlcv(DEFAULT_BENCHMARK, start=start, end=end)
        if not bm.empty:
            bm_equity = (1 + bm["close"].pct_change().fillna(0)).cumprod()
        else:
            bm_equity = pd.Series()

        metrics = compute_metrics(trade_df, equity, bm_equity)

        return {
            "status": "ok",
            "ticker": ticker,
            "strategy": strategy.name,
            "initial_capital": initial_capital,
            "final_equity": round(equity.iloc[-1], 2),
            "equity_curve": equity,
            "trade_history": trade_df,
            "metrics": metrics,
        }
