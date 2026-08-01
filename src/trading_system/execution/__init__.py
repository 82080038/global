"""Execution layer - Trading execution interfaces and implementations.

This module provides:
- TradingInterface: Abstract base class for execution modes
- RealExecutionEngine: Real trading via broker APIs
- PaperExecutionEngine: Paper trading simulation
- get_execution_engine(): Factory function to select engine based on TRADING_MODE
"""

import os

from trading_system.config import TRADING_CAPITAL, TRADING_MODE
from trading_system.data.storage import DataStorage
from trading_system.execution.interface import TradingInterface
from trading_system.execution.paper_execution import PaperExecutionEngine
from trading_system.execution.real_execution import RealExecutionEngine


def get_execution_engine(
    storage: DataStorage | None = None,
    capital: float = TRADING_CAPITAL,
    mode: str | None = None,
) -> TradingInterface:
    """Factory function to get the appropriate execution engine.

    Args:
        storage: DataStorage instance for database operations
        capital: Trading capital (default from config)
        mode: Override TRADING_MODE ("paper" or "real")

    Returns:
        TradingInterface implementation based on TRADING_MODE or mode parameter

    Example:
        >>> executor = get_execution_engine()
        >>> result = executor.execute_order({"ticker": "BBCA.JK", "action": "buy", "shares": 100, "target_price": 9000})
    """
    execution_mode = (mode or TRADING_MODE).lower()

    if execution_mode == "real":
        return RealExecutionEngine(storage, capital)
    elif execution_mode == "paper":
        return PaperExecutionEngine(storage, capital)
    else:
        raise ValueError(f"Invalid TRADING_MODE: {execution_mode}. Must be 'paper' or 'real'.")


__all__ = [
    "TradingInterface",
    "RealExecutionEngine",
    "PaperExecutionEngine",
    "get_execution_engine",
]
