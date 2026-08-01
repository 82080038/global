"""Circuit Breaker — adopted from ML app, adapted for trading-system.

Halts trading when extreme market events occur (IHSG crash, individual stock
auto-rejection, or trading halt thresholds).

Integrates with:
  - analysis/no_trade.py (no-trade zone detection)
  - risk/engine.py (risk management)
  - execution/automated.py (auto-trade guard)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Circuit breaker for market-wide and individual stock extreme events.

    IDX-specific thresholds:
      - IHSG drop > 3%: caution mode
      - IHSG drop > 5%: trading halt
      - Individual stock drop > 20%: auto-rejection (already enforced by IDX)
    """

    def __init__(
        self,
        ihsg_drop_threshold: float = 0.03,
        individual_stock_drop_threshold: float = 0.20,
        trading_halt_threshold: float = 0.05,
    ) -> None:
        self.ihsg_drop_threshold = ihsg_drop_threshold
        self.individual_stock_drop_threshold = individual_stock_drop_threshold
        self.trading_halt_threshold = trading_halt_threshold

        self.circuit_breaker_active = False
        self.circuit_breaker_reason: str | None = None
        self.last_ihsg_value: float | None = None
        self.activated_at: datetime | None = None

    def check_circuit_breaker(
        self,
        current_ihsg: float,
        symbol: str | None = None,
        symbol_price_change: float | None = None,
    ) -> tuple[bool, str | None, str]:
        """Check circuit breaker conditions.

        Returns:
            Tuple of (should_trade, reason, action)
        """
        action = "NORMAL"

        if self.last_ihsg_value is not None:
            ihsg_change = (current_ihsg - self.last_ihsg_value) / self.last_ihsg_value

            if ihsg_change < -self.trading_halt_threshold:
                self.circuit_breaker_active = True
                self.circuit_breaker_reason = (
                    f"IHSG drop {ihsg_change:.2%} exceeds halt threshold {self.trading_halt_threshold:.2%}"
                )
                self.activated_at = datetime.now()
                action = "HALT"
                logger.warning("Circuit breaker HALT: %s", self.circuit_breaker_reason)
                return False, self.circuit_breaker_reason, action

            if ihsg_change < -self.ihsg_drop_threshold:
                action = "CAUTION"
                logger.warning(
                    "Circuit breaker CAUTION: IHSG drop %.2f%%", ihsg_change * 100
                )

        if symbol and symbol_price_change is not None:
            if symbol_price_change < -self.individual_stock_drop_threshold:
                self.circuit_breaker_active = True
                self.circuit_breaker_reason = (
                    f"{symbol} drop {symbol_price_change:.2%} hits auto-rejection"
                )
                self.activated_at = datetime.now()
                action = "HALT"
                logger.warning("Circuit breaker HALT: %s", self.circuit_breaker_reason)
                return False, self.circuit_breaker_reason, action

        self.last_ihsg_value = current_ihsg
        return True, None, action

    def reset(self) -> None:
        self.circuit_breaker_active = False
        self.circuit_breaker_reason = None
        self.activated_at = None

    def status(self) -> dict[str, Any]:
        return {
            "active": self.circuit_breaker_active,
            "reason": self.circuit_breaker_reason,
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "last_ihsg": self.last_ihsg_value,
            "thresholds": {
                "ihsg_drop": self.ihsg_drop_threshold,
                "stock_drop": self.individual_stock_drop_threshold,
                "halt": self.trading_halt_threshold,
            },
        }
