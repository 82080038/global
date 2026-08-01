"""Paper Execution Engine - Simulation mode.

Implements TradingInterface for paper trading (simulation) without real money.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from trading_system.config import TRADING_CAPITAL
from trading_system.data.storage import DataStorage
from trading_system.decision.engine import DecisionEngine
from trading_system.execution.engine import ExecutionEngine
from trading_system.execution.interface import TradingInterface

logger = logging.getLogger(__name__)


class PaperExecutionEngine(TradingInterface):
    """Paper trading execution engine for simulation without real money.

    Simulates order execution with realistic fills, fees, and slippage
    without actual broker API calls or real money transactions.
    """

    name = "paper_execution"

    def __init__(self, storage: DataStorage | None = None, cash: float = TRADING_CAPITAL):
        self.storage = storage or DataStorage()
        self.cash = cash
        self.execution = ExecutionEngine()
        self.decision = DecisionEngine(storage)

        # In-memory paper trading state (could also be persisted to DB)
        self._paper_positions: dict[str, dict] = {}
        self._paper_cash = cash
        self._paper_orders: list[dict] = []

    def execute_order(self, order: dict) -> dict:
        """Execute a paper trading order (simulation).

        Args:
            order: Order dictionary with ticker, action, shares, target_price, etc.

        Returns:
            Simulated execution result with order_id, filled_price, fees, etc.
        """
        ticker = order.get("ticker")
        action = order.get("action", "").lower()
        shares = order.get("shares", 0)
        target_price = order.get("target_price", 0)

        if not ticker or shares <= 0 or target_price <= 0:
            return {
                "status": "error",
                "message": "Invalid order parameters",
                "order": order,
            }

        # Get latest price from market
        df = self.storage.load_ohlcv(ticker)
        if df.empty:
            return {
                "status": "error",
                "message": f"No OHLCV data for {ticker}",
                "order": order,
            }

        last_price = float(df["close"].iloc[-1])
        avg_daily_value = df["volume"].tail(20).mean() * last_price

        # Check feasibility
        feasibility = self.execution.check_feasibility(order, self._paper_cash, avg_daily_value)

        if not feasibility.get("feasible"):
            return {
                "status": "error",
                "message": feasibility.get("reason", "Order not feasible"),
                "feasibility": feasibility,
            }

        # Simulate fill
        fill = self.execution.simulate_fill(order, last_price, avg_daily_value)

        # Generate paper order ID
        order_id = f"PAPER_{ticker}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

        # Update paper trading state
        if action == "buy":
            cost = fill.get("filled_price", last_price) * shares + fill.get("total_fees", 0)
            if cost > self._paper_cash:
                return {
                    "status": "error",
                    "message": f"Insufficient paper cash: {self._paper_cash:.2f} needed: {cost:.2f}",
                }

            self._paper_cash -= cost

            if ticker in self._paper_positions:
                # Add to existing position
                existing = self._paper_positions[ticker]
                total_shares = existing["shares"] + shares
                avg_price = (
                    (existing["avg_price"] * existing["shares"] + fill.get("filled_price", last_price) * shares)
                    / total_shares
                )
                self._paper_positions[ticker] = {
                    "shares": total_shares,
                    "avg_price": avg_price,
                    "stop_loss": order.get("stop_loss"),
                    "take_profit": order.get("take_profit"),
                    "created_at": existing["created_at"],
                }
            else:
                # New position
                self._paper_positions[ticker] = {
                    "shares": shares,
                    "avg_price": fill.get("filled_price", last_price),
                    "stop_loss": order.get("stop_loss"),
                    "take_profit": order.get("take_profit"),
                    "created_at": datetime.now(UTC).isoformat(),
                }

        elif action == "sell":
            if ticker not in self._paper_positions:
                return {
                    "status": "error",
                    "message": f"No paper position for {ticker}",
                }

            position = self._paper_positions[ticker]
            if shares > position["shares"]:
                return {
                    "status": "error",
                    "message": f"Cannot sell {shares} shares, only {position['shares']} available",
                }

            proceeds = fill.get("filled_price", last_price) * shares - fill.get("total_fees", 0)
            self._paper_cash += proceeds

            # Update or close position
            remaining = position["shares"] - shares
            if remaining <= 0:
                del self._paper_positions[ticker]
            else:
                self._paper_positions[ticker]["shares"] = remaining

        # Record paper order
        self._paper_orders.append({
            "order_id": order_id,
            "ticker": ticker,
            "action": action,
            "shares": shares,
            "filled_price": fill.get("filled_price"),
            "fees": fill.get("total_fees"),
            "timestamp": datetime.now(UTC).isoformat(),
        })

        logger.info(f"Paper execution: {action.upper()} {shares} {ticker} @ {fill.get('filled_price')}")

        return {
            "status": "ok",
            "order_id": order_id,
            "filled_price": fill.get("filled_price"),
            "filled_shares": fill.get("filled_shares"),
            "fees": fill.get("total_fees"),
            "message": f"Paper order executed successfully",
        }

    def get_position(self, ticker: str) -> dict | None:
        """Get current paper position for a ticker."""
        if ticker not in self._paper_positions:
            return None

        position = self._paper_positions[ticker]

        # Calculate unrealized PnL
        df = self.storage.load_ohlcv(ticker)
        if df.empty:
            current_price = position["avg_price"]
        else:
            current_price = float(df["close"].iloc[-1])

        shares = position["shares"]
        unrealized_pnl = (current_price - position["avg_price"]) * shares

        return {
            "ticker": ticker,
            "shares": shares,
            "avg_price": position["avg_price"],
            "current_price": current_price,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pnl_pct": (current_price / position["avg_price"] - 1) * 100 if position["avg_price"] > 0 else 0,
            "stop_loss": position.get("stop_loss"),
            "take_profit": position.get("take_profit"),
            "created_at": position.get("created_at"),
            "status": "OPEN",
        }

    def get_portfolio_summary(self) -> dict:
        """Get overall paper portfolio summary."""
        total_value = self._paper_cash
        total_pnl = 0.0

        position_details = []
        for ticker, position in self._paper_positions.items():
            position_detail = self.get_position(ticker)
            if position_detail:
                position_details.append(position_detail)
                total_value += position_detail["current_price"] * position_detail["shares"]
                total_pnl += position_detail.get("unrealized_pnl", 0)

        return {
            "total_value": total_value,
            "cash_balance": self._paper_cash,
            "positions_count": len(position_details),
            "total_pnl": total_pnl,
            "positions": position_details,
            "initial_capital": self.cash,
            "return_pct": (total_value / self.cash - 1) * 100 if self.cash > 0 else 0,
        }

    def cancel_order(self, order_id: str) -> dict:
        """Cancel a pending paper order.

        Note: In current implementation, paper orders are executed immediately,
        so cancellation is not applicable.
        """
        return {
            "status": "error",
            "message": "Order cancellation not supported - paper orders are executed immediately",
            "order_id": order_id,
        }

    def reset(self) -> dict:
        """Reset paper trading state to initial conditions.

        Returns:
            Reset confirmation with initial capital restored.
        """
        self._paper_positions.clear()
        self._paper_cash = self.cash
        self._paper_orders.clear()

        logger.info(f"Paper trading reset to initial capital: {self.cash}")

        return {
            "status": "ok",
            "message": "Paper trading state reset",
            "initial_capital": self.cash,
        }
