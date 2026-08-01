"""Broker API Adapters — abstraction layer for real broker integration.

Defines a common interface for broker APIs so the RealExecutionEngine can
switch between brokers via configuration. Currently ships with a
MockBrokerAdapter (for testing) and stubs for common Indonesian brokers.

Supported brokers (planned):
    - Sinarmas Sekuritas
    - BNI Sekuritas (SmartPlus)
    - Mirae Asset Sekuritas
    - IPOT (Indo Premier)
    - Stockbit

Environment variables:
    BROKER_ADAPTER       — broker name (default: "mock")
    BROKER_API_KEY       — broker API key
    BROKER_API_SECRET    — broker API secret
    BROKER_ACCOUNT_ID    — broker account ID
    BROKER_BASE_URL      — broker API base URL (optional override)

Usage:
    from trading_system.execution.broker_adapter import get_broker_adapter
    adapter = get_broker_adapter()
    result = adapter.place_order(ticker="BBCA.JK", action="buy", shares=100, price=8000)
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BrokerOrder:
    """Normalized broker order representation."""

    ticker: str
    action: str  # "buy" or "sell"
    shares: int
    price: float
    order_type: str = "limit"  # "limit" or "market"
    time_in_force: str = "DAY"  # "DAY", "GTC", "IOC"
    stop_loss: float | None = None
    take_profit: float | None = None


@dataclass
class BrokerOrderResult:
    """Normalized broker order result."""

    status: str  # "ok", "error", "pending", "rejected"
    broker_order_id: str | None = None
    filled_price: float | None = None
    filled_shares: int | None = None
    fees: float = 0.0
    message: str = ""
    raw_response: dict | None = None


@dataclass
class BrokerPosition:
    """Normalized broker position representation."""

    ticker: str
    shares: int
    avg_price: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float


@dataclass
class BrokerAccount:
    """Normalized broker account summary."""

    cash_balance: float
    total_equity: float
    total_market_value: float
    buying_power: float
    currency: str = "IDR"
    account_id: str | None = None


class BrokerAdapter(ABC):
    """Abstract base class for broker API adapters.

    All broker integrations must implement this interface so the
    RealExecutionEngine can switch between brokers via configuration.
    """

    name: str = "base"

    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate with broker API. Returns True on success."""
        pass

    @abstractmethod
    def get_account(self) -> BrokerAccount:
        """Get account summary (cash, equity, buying power)."""
        pass

    @abstractmethod
    def get_position(self, ticker: str) -> BrokerPosition | None:
        """Get current position for a ticker from broker."""
        pass

    @abstractmethod
    def get_all_positions(self) -> list[BrokerPosition]:
        """Get all open positions from broker."""
        pass

    @abstractmethod
    def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        """Place an order with the broker."""
        pass

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> BrokerOrderResult:
        """Cancel a pending order with the broker."""
        pass

    @abstractmethod
    def get_order_status(self, broker_order_id: str) -> BrokerOrderResult:
        """Get status of a placed order."""
        pass

    @abstractmethod
    def get_cash_balance(self) -> float:
        """Get current cash balance from broker."""
        pass


class MockBrokerAdapter(BrokerAdapter):
    """Mock broker adapter for testing and development.

    Simulates broker responses without making real API calls.
    Useful for integration testing and dry-run mode.
    """

    name = "mock"

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        account_id: str | None = None,
        base_url: str | None = None,
    ):
        self.api_key = api_key or os.getenv("BROKER_API_KEY", "mock_key")
        self.api_secret = api_secret or os.getenv("BROKER_API_SECRET", "mock_secret")
        self.account_id = account_id or os.getenv("BROKER_ACCOUNT_ID", "MOCK-001")
        self._authenticated = False
        self._cash = 100_000_000.0  # Rp 100M mock cash
        self._positions: dict[str, BrokerPosition] = {}
        self._orders: dict[str, BrokerOrderResult] = {}
        self._order_counter = 0

        logger.info(f"MockBrokerAdapter initialized (account: {self.account_id})")

    def authenticate(self) -> bool:
        self._authenticated = True
        logger.info("MockBrokerAdapter: authenticated (mock)")
        return True

    def get_account(self) -> BrokerAccount:
        if not self._authenticated:
            self.authenticate()
        market_value = sum(p.market_value for p in self._positions.values())
        return BrokerAccount(
            cash_balance=self._cash,
            total_equity=self._cash + market_value,
            total_market_value=market_value,
            buying_power=self._cash,
            currency="IDR",
            account_id=self.account_id,
        )

    def get_position(self, ticker: str) -> BrokerPosition | None:
        return self._positions.get(ticker)

    def get_all_positions(self) -> list[BrokerPosition]:
        return list(self._positions.values())

    def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        if not self._authenticated:
            self.authenticate()

        self._order_counter += 1
        broker_order_id = f"MOCK-{self._order_counter:06d}"

        # Simulate fill at target price
        filled_price = order.price
        filled_shares = order.shares
        fees = filled_price * filled_shares * 0.0015  # 0.15% commission

        # Update mock state
        if order.action == "buy":
            cost = filled_price * filled_shares + fees
            if cost > self._cash:
                return BrokerOrderResult(
                    status="rejected",
                    message=f"Insufficient cash: need {cost}, have {self._cash}",
                )
            self._cash -= cost
            existing = self._positions.get(order.ticker)
            if existing:
                total_shares = existing.shares + filled_shares
                new_avg = (existing.avg_price * existing.shares + filled_price * filled_shares) / total_shares
                self._positions[order.ticker] = BrokerPosition(
                    ticker=order.ticker,
                    shares=total_shares,
                    avg_price=new_avg,
                    current_price=filled_price,
                    market_value=filled_price * total_shares,
                    unrealized_pnl=0.0,
                    unrealized_pnl_pct=0.0,
                )
            else:
                self._positions[order.ticker] = BrokerPosition(
                    ticker=order.ticker,
                    shares=filled_shares,
                    avg_price=filled_price,
                    current_price=filled_price,
                    market_value=filled_price * filled_shares,
                    unrealized_pnl=0.0,
                    unrealized_pnl_pct=0.0,
                )
        elif order.action == "sell":
            existing = self._positions.get(order.ticker)
            if not existing or existing.shares < filled_shares:
                return BrokerOrderResult(
                    status="rejected",
                    message=f"Insufficient shares: have {existing.shares if existing else 0}, selling {filled_shares}",
                )
            proceeds = filled_price * filled_shares - fees
            self._cash += proceeds
            remaining = existing.shares - filled_shares
            if remaining <= 0:
                del self._positions[order.ticker]
            else:
                self._positions[order.ticker] = BrokerPosition(
                    ticker=order.ticker,
                    shares=remaining,
                    avg_price=existing.avg_price,
                    current_price=filled_price,
                    market_value=filled_price * remaining,
                    unrealized_pnl=(filled_price - existing.avg_price) * remaining,
                    unrealized_pnl_pct=(filled_price / existing.avg_price - 1) * 100 if existing.avg_price > 0 else 0,
                )

        result = BrokerOrderResult(
            status="ok",
            broker_order_id=broker_order_id,
            filled_price=filled_price,
            filled_shares=filled_shares,
            fees=fees,
            message=f"Order filled (mock)",
        )
        self._orders[broker_order_id] = result
        logger.info(f"MockBrokerAdapter: {order.action} {filled_shares} {order.ticker} @ {filled_price} (id={broker_order_id})")
        return result

    def cancel_order(self, broker_order_id: str) -> BrokerOrderResult:
        return BrokerOrderResult(
            status="error",
            message="Mock orders are filled immediately - cannot cancel",
            broker_order_id=broker_order_id,
        )

    def get_order_status(self, broker_order_id: str) -> BrokerOrderResult:
        return self._orders.get(
            broker_order_id,
            BrokerOrderResult(status="error", message="Order not found"),
        )

    def get_cash_balance(self) -> float:
        return self._cash


class SinarmasBrokerAdapter(BrokerAdapter):
    """Sinarmas Sekuritas broker adapter (stub).

    TODO: Implement actual API integration when Sinarmas provides API access.
    Currently returns NotImplementedError for all methods.

    Reference: https://www.sinarmassekuritas.co.id/
    Required env vars:
        BROKER_API_KEY, BROKER_API_SECRET, BROKER_ACCOUNT_ID
    """

    name = "sinarmas"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key") or os.getenv("BROKER_API_KEY")
        self.api_secret = kwargs.get("api_secret") or os.getenv("BROKER_API_SECRET")
        self.account_id = kwargs.get("account_id") or os.getenv("BROKER_ACCOUNT_ID")
        self.base_url = kwargs.get("base_url") or "https://api.sinarmassekuritas.co.id/v1"
        logger.warning("SinarmasBrokerAdapter: stub implementation - not yet integrated")

    def authenticate(self) -> bool:
        raise NotImplementedError("Sinarmas broker API not yet implemented")

    def get_account(self) -> BrokerAccount:
        raise NotImplementedError("Sinarmas broker API not yet implemented")

    def get_position(self, ticker: str) -> BrokerPosition | None:
        raise NotImplementedError("Sinarmas broker API not yet implemented")

    def get_all_positions(self) -> list[BrokerPosition]:
        raise NotImplementedError("Sinarmas broker API not yet implemented")

    def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        raise NotImplementedError("Sinarmas broker API not yet implemented")

    def cancel_order(self, broker_order_id: str) -> BrokerOrderResult:
        raise NotImplementedError("Sinarmas broker API not yet implemented")

    def get_order_status(self, broker_order_id: str) -> BrokerOrderResult:
        raise NotImplementedError("Sinarmas broker API not yet implemented")

    def get_cash_balance(self) -> float:
        raise NotImplementedError("Sinarmas broker API not yet implemented")


class BNISekuritasBrokerAdapter(BrokerAdapter):
    """BNI Sekuritas (SmartPlus) broker adapter (stub).

    TODO: Implement actual API integration when BNI Sekuritas provides API access.
    Reference: https://www.bnisekuritas.co.id/
    """

    name = "bni_sekuritas"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key") or os.getenv("BROKER_API_KEY")
        self.api_secret = kwargs.get("api_secret") or os.getenv("BROKER_API_SECRET")
        self.account_id = kwargs.get("account_id") or os.getenv("BROKER_ACCOUNT_ID")
        self.base_url = kwargs.get("base_url") or "https://api.bnisekuritas.co.id/v1"
        logger.warning("BNISekuritasBrokerAdapter: stub implementation - not yet integrated")

    def authenticate(self) -> bool:
        raise NotImplementedError("BNI Sekuritas broker API not yet implemented")

    def get_account(self) -> BrokerAccount:
        raise NotImplementedError("BNI Sekuritas broker API not yet implemented")

    def get_position(self, ticker: str) -> BrokerPosition | None:
        raise NotImplementedError("BNI Sekuritas broker API not yet implemented")

    def get_all_positions(self) -> list[BrokerPosition]:
        raise NotImplementedError("BNI Sekuritas broker API not yet implemented")

    def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        raise NotImplementedError("BNI Sekuritas broker API not yet implemented")

    def cancel_order(self, broker_order_id: str) -> BrokerOrderResult:
        raise NotImplementedError("BNI Sekuritas broker API not yet implemented")

    def get_order_status(self, broker_order_id: str) -> BrokerOrderResult:
        raise NotImplementedError("BNI Sekuritas broker API not yet implemented")

    def get_cash_balance(self) -> float:
        raise NotImplementedError("BNI Sekuritas broker API not yet implemented")


# Registry of available broker adapters
_BROKER_REGISTRY: dict[str, type[BrokerAdapter]] = {
    "mock": MockBrokerAdapter,
    "sinarmas": SinarmasBrokerAdapter,
    "bni_sekuritas": BNISekuritasBrokerAdapter,
}


def get_broker_adapter(broker_name: str | None = None) -> BrokerAdapter:
    """Get a broker adapter instance by name.

    Args:
        broker_name: Broker name (default: from BROKER_ADAPTER env var or "mock")

    Returns:
        BrokerAdapter instance

    Raises:
        ValueError: If broker name is not in registry
    """
    name = broker_name or os.getenv("BROKER_ADAPTER", "mock")
    if name not in _BROKER_REGISTRY:
        raise ValueError(
            f"Unknown broker adapter: {name}. Available: {list(_BROKER_REGISTRY.keys())}"
        )
    adapter_class = _BROKER_REGISTRY[name]
    return adapter_class()


def list_available_brokers() -> list[str]:
    """List all registered broker adapter names."""
    return list(_BROKER_REGISTRY.keys())
