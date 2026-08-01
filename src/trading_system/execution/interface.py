"""Shared interface for trading execution modes.

This module defines the abstract base class that both real and paper trading
engines must implement, allowing seamless switching between modes via configuration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class TradingInterface(ABC):
    """Abstract base class for trading execution interfaces.

    Both real execution (via broker API) and paper trading (simulation)
    must implement this interface to ensure consistent behavior across modes.
    """

    @abstractmethod
    def execute_order(self, order: dict) -> dict:
        """Execute a trading order (real or paper).

        Args:
            order: Dictionary containing order details:
                - ticker: str
                - action: str ("buy" or "sell")
                - shares: int
                - target_price: float
                - stop_loss: float | None
                - take_profit: float | None

        Returns:
            Dictionary containing execution result:
                - status: str ("ok" or "error")
                - order_id: str | None
                - filled_price: float | None
                - filled_shares: int | None
                - fees: float
                - message: str | None
        """
        pass

    @abstractmethod
    def get_position(self, ticker: str) -> dict | None:
        """Get current position for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Position dictionary or None if no position exists:
                - ticker: str
                - shares: int
                - avg_price: float
                - unrealized_pnl: float
                - created_at: str
        """
        pass

    @abstractmethod
    def get_portfolio_summary(self) -> dict:
        """Get overall portfolio summary.

        Returns:
            Dictionary containing:
                - total_value: float
                - cash_balance: float
                - positions_count: int
                - total_pnl: float
                - positions: list[dict]
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> dict:
        """Cancel a pending order.

        Args:
            order_id: Order identifier

        Returns:
            Dictionary containing cancellation result:
                - status: str ("ok" or "error")
                - message: str
        """
        pass
