"""Real Execution Engine - Broker API integration.

Implements TradingInterface for real trading via broker APIs.
Currently uses database persistence as the "broker" for production safety.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

from trading_system.config import TRADING_CAPITAL
from trading_system.data.storage import DataStorage
from trading_system.execution.engine import ExecutionEngine
from trading_system.execution.interface import TradingInterface
from trading_system.risk.costs import get_default_cost_model

logger = logging.getLogger(__name__)


class RealExecutionEngine(TradingInterface):
    """Real trading execution engine using broker APIs.

    For production safety, currently uses database persistence as the broker.
    In production, this would integrate with actual broker APIs (Sekuritas, etc.).
    """

    name = "real_execution"

    def __init__(self, storage: DataStorage | None = None, capital: float = TRADING_CAPITAL, cash: float = TRADING_CAPITAL):
        self.storage = storage or DataStorage()
        self.capital = capital
        self.execution = ExecutionEngine()
        self.auto_trade_enabled = os.getenv("AUTO_TRADE_ENABLED", "false").lower() == "true"

        if not self.auto_trade_enabled:
            logger.warning("AUTO_TRADE_ENABLED=false. Real execution DISABLED (monitoring mode).")

    def execute_order(self, order: dict) -> dict:
        """Execute a real trading order via broker API.

        Args:
            order: Order dictionary with ticker, action, shares, target_price, etc.

        Returns:
            Execution result with order_id, filled_price, fees, etc.
        """
        if not self.auto_trade_enabled:
            return {
                "status": "skipped",
                "message": "AUTO_TRADE_ENABLED=false - execution disabled (monitoring mode)",
                "order": order,
            }

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
        cash = self.storage.get_cash_balance() or self.capital
        feasibility = self.execution.check_feasibility(order, cash, avg_daily_value)

        if not feasibility.get("feasible"):
            return {
                "status": "error",
                "message": feasibility.get("reason", "Order not feasible"),
                "feasibility": feasibility,
            }

        # Simulate fill (in production, this would call broker API)
        fill = self.execution.simulate_fill(order, last_price, avg_daily_value)

        # Save order to database
        order_id = self.storage.save_order(
            ticker=ticker,
            order_type=action.upper(),
            quantity=shares,
            price=fill.get("filled_price", last_price),
            fee=fill.get("total_fees", 0),
            trigger="REAL_EXECUTION",
        )

        # Update position
        if action == "buy":
            self.storage.save_position(
                ticker=ticker,
                quantity=shares,
                avg_entry_price=fill.get("filled_price", last_price),
                stop_loss=order.get("stop_loss"),
                take_profit=order.get("take_profit"),
            )
        elif action == "sell":
            position = self.storage.get_open_position(ticker)
            if position:
                entry_price = position.get("avg_entry_price", 0)
                realized_pnl = (fill.get("filled_price", last_price) - entry_price) * shares
                remaining = position.get("quantity", 0) - shares

                if remaining <= 0:
                    self.storage.update_position(
                        position["id"],
                        status="CLOSED",
                        quantity=0,
                        current_price=fill.get("filled_price", last_price),
                        realized_pnl=realized_pnl,
                    )
                else:
                    self.storage.update_position(
                        position["id"],
                        quantity=remaining,
                        current_price=fill.get("filled_price", last_price),
                        realized_pnl=realized_pnl,
                    )

        # Audit log
        self.storage.audit("real_execution.order_executed", {
            "order_id": order_id,
            "ticker": ticker,
            "action": action,
            "shares": shares,
            "filled_price": fill.get("filled_price"),
            "fees": fill.get("total_fees"),
        })

        logger.info(f"Real execution: {action.upper()} {shares} {ticker} @ {fill.get('filled_price')}")

        return {
            "status": "ok",
            "order_id": order_id,
            "filled_price": fill.get("filled_price"),
            "filled_shares": fill.get("filled_shares"),
            "fees": fill.get("total_fees"),
            "message": f"Order executed successfully",
        }

    def get_position(self, ticker: str) -> dict | None:
        """Get current position for a ticker."""
        position = self.storage.get_open_position(ticker)
        if not position:
            return None

        # Calculate unrealized PnL
        df = self.storage.load_ohlcv(ticker)
        if df.empty:
            current_price = position.get("avg_entry_price", 0)
        else:
            current_price = float(df["close"].iloc[-1])

        entry_price = position.get("avg_entry_price", 0)
        shares = position.get("quantity", 0)
        unrealized_pnl = (current_price - entry_price) * shares

        return {
            "ticker": ticker,
            "shares": shares,
            "avg_price": entry_price,
            "current_price": current_price,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pnl_pct": (current_price / entry_price - 1) * 100 if entry_price > 0 else 0,
            "stop_loss": position.get("stop_loss"),
            "take_profit": position.get("take_profit"),
            "created_at": position.get("created_at"),
            "status": position.get("status", "OPEN"),
        }

    def get_portfolio_summary(self) -> dict:
        """Get overall portfolio summary."""
        positions = self.storage.get_all_positions()
        cash = self.storage.get_cash_balance() or self.capital

        total_value = cash
        total_pnl = 0.0

        position_details = []
        for pos in positions:
            ticker = pos.get("ticker")
            position_detail = self.get_position(ticker)
            if position_detail:
                position_details.append(position_detail)
                total_value += position_detail["current_price"] * position_detail["shares"]
                total_pnl += position_detail.get("realized_pnl", 0) + position_detail.get("unrealized_pnl", 0)

        return {
            "total_value": total_value,
            "cash_balance": cash,
            "positions_count": len(position_details),
            "total_pnl": total_pnl,
            "positions": position_details,
        }

    def cancel_order(self, order_id: str) -> dict:
        """Cancel a pending order.

        Note: In current implementation, orders are executed immediately,
        so cancellation is not applicable. This is included for interface
        compatibility and future broker API integration.
        """
        return {
            "status": "error",
            "message": "Order cancellation not supported - orders are executed immediately",
            "order_id": order_id,
        }
