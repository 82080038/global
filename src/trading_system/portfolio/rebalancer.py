"""Portfolio Rebalancer — Penyeimbangan portofolio berkala ke bobot target.

Membaca target bobot dari env var REBALANCE_TARGET_WEIGHTS (JSON),
menghitung selisih dengan posisi saat ini, dan mengeksekusi order
untuk menyeimbangkan portofolio.

Gunakan REBALANCE_ENABLED=true di .env untuk mengaktifkan.
"""

from __future__ import annotations

import json
import logging
import os

from trading_system.config import DEFAULT_BROKER_FEE_BUY, DEFAULT_BROKER_FEE_SELL, DEFAULT_LEVY
from trading_system.data.storage import DataStorage

logger = logging.getLogger(__name__)


class PortfolioRebalancer:
    """Rebalance portfolio to target weights periodically.

    Example target weights (JSON in env):
        {"BBCA.JK": 0.4, "TLKM.JK": 0.3, "ASII.JK": 0.3}
    """

    name = "rebalancer"

    def __init__(self, storage: DataStorage | None = None):
        self.storage = storage or DataStorage()

        weights_str = os.getenv("REBALANCE_TARGET_WEIGHTS", "{}")
        try:
            self.target_weights: dict[str, float] = json.loads(weights_str) if weights_str else {}
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Invalid REBALANCE_TARGET_WEIGHTS JSON: {weights_str}")
            self.target_weights = {}

        self.rebalance_enabled = os.getenv("REBALANCE_ENABLED", "false").lower() == "true"
        self.rebalance_frequency = os.getenv("REBALANCE_FREQUENCY", "monthly")

        if not self.rebalance_enabled:
            logger.info("REBALANCE_ENABLED=false. Rebalancing dinonaktifkan.")

    def _get_latest_price(self, ticker: str) -> float | None:
        """Get latest close price from OHLCV data."""
        df = self.storage.load_ohlcv(ticker)
        if df.empty:
            return None
        return float(df["close"].iloc[-1])

    def get_current_portfolio_value(self) -> float:
        """Calculate total value of all open positions."""
        positions = self.storage.get_all_open_positions()
        total = 0.0
        for pos in positions:
            price = self._get_latest_price(pos["ticker"])
            if price:
                total += price * pos["quantity"]
        return total

    def get_current_weights(self) -> dict[str, float]:
        """Calculate current portfolio weights based on market value."""
        positions = self.storage.get_all_open_positions()
        total_value = 0.0
        values: dict[str, float] = {}

        for pos in positions:
            price = self._get_latest_price(pos["ticker"])
            if price:
                val = price * pos["quantity"]
                values[pos["ticker"]] = val
                total_value += val

        if total_value <= 0:
            return {}

        return {ticker: val / total_value for ticker, val in values.items()}

    def _get_target_quantity(self, total_value: float, ticker: str, price: float) -> int:
        """Calculate target quantity based on target weight."""
        target_weight = self.target_weights.get(ticker, 0)
        target_value = total_value * target_weight
        if price > 0 and target_value > 0:
            return int(target_value / price // 100) * 100  # Round to lot
        return 0

    def _execute_rebalance_buy(self, ticker: str, quantity: int, price: float) -> dict:
        """Execute a rebalance BUY order."""
        if quantity <= 0:
            return {"status": "skipped", "reason": "quantity is 0"}

        order_value = quantity * price
        fee = order_value * (DEFAULT_BROKER_FEE_BUY + DEFAULT_LEVY)

        order_id = self.storage.save_order(
            ticker=ticker, order_type="BUY", quantity=quantity, price=price,
            fee=fee, trigger="REBALANCE", order_style="REBALANCE",
        )

        # Check if position already exists
        existing = self.storage.get_open_position(ticker)
        if existing:
            old_qty = existing["quantity"]
            old_entry = existing["avg_entry_price"]
            new_qty = old_qty + quantity
            new_entry = (old_entry * old_qty + price * quantity) / new_qty
            self.storage.update_position(
                existing["id"], quantity=new_qty, avg_entry_price=new_entry,
                current_price=price,
            )
        else:
            self.storage.save_position(
                ticker=ticker, quantity=quantity, avg_entry_price=price,
                stop_loss=price * 0.95, take_profit=price * 1.10,
            )

        self.storage.audit("rebalance.buy", {
            "order_id": order_id, "ticker": ticker,
            "quantity": quantity, "price": price, "fee": fee,
        })

        logger.info(f"REBALANCE BUY {quantity} {ticker} @ Rp {price:,.2f}")

        # Telegram notification
        try:
            from trading_system.utils.notifier import send_telegram
            send_telegram(
                f"🔄 <b>REBALANCING</b>\nBUY {quantity} {ticker} @ Rp {price:,.2f}\nTotal: Rp {order_value:,.2f}",
                parse_mode="HTML",
            )
        except Exception:
            pass

        return {
            "status": "ok", "action": "BUY", "ticker": ticker,
            "quantity": quantity, "price": price, "fee": fee,
            "order_id": order_id,
        }

    def _execute_rebalance_sell(self, ticker: str, quantity: int, price: float) -> dict:
        """Execute a rebalance SELL order."""
        if quantity <= 0:
            return {"status": "skipped", "reason": "quantity is 0"}

        position = self.storage.get_open_position(ticker)
        if not position or position["quantity"] < quantity:
            logger.warning(f"Rebalance SELL {ticker}: insufficient quantity")
            return {"status": "skipped", "reason": "insufficient quantity"}

        order_value = quantity * price
        fee = order_value * (DEFAULT_BROKER_FEE_SELL + DEFAULT_LEVY + 0.001)

        order_id = self.storage.save_order(
            ticker=ticker, order_type="SELL", quantity=quantity, price=price,
            fee=fee, trigger="REBALANCE", order_style="REBALANCE",
        )

        entry = position.get("avg_entry_price", 0)
        realized_pnl = (price - entry) * quantity
        remaining = position["quantity"] - quantity

        if remaining <= 0:
            self.storage.update_position(
                position["id"], status="CLOSED", quantity=0,
                current_price=price, realized_pnl=realized_pnl,
            )
        else:
            self.storage.update_position(
                position["id"], quantity=remaining,
                current_price=price, realized_pnl=realized_pnl,
            )

        self.storage.audit("rebalance.sell", {
            "order_id": order_id, "ticker": ticker,
            "quantity": quantity, "price": price, "fee": fee,
            "realized_pnl": realized_pnl,
        })

        logger.info(f"REBALANCE SELL {quantity} {ticker} @ Rp {price:,.2f} (PnL: {realized_pnl:,.0f})")

        try:
            from trading_system.utils.notifier import send_telegram
            send_telegram(
                f"🔄 <b>REBALANCING</b>\nSELL {quantity} {ticker} @ Rp {price:,.2f}\nTotal: Rp {order_value:,.2f}",
                parse_mode="HTML",
            )
        except Exception:
            pass

        return {
            "status": "ok", "action": "SELL", "ticker": ticker,
            "quantity": quantity, "price": price, "fee": fee,
            "realized_pnl": realized_pnl, "order_id": order_id,
        }

    def run_rebalance(self) -> list[dict]:
        """Run rebalancing cycle. Returns list of executed orders.

        Requires REBALANCE_ENABLED=true and REBALANCE_TARGET_WEIGHTS set.
        """
        if not self.rebalance_enabled:
            logger.info("Rebalancing disabled. Set REBALANCE_ENABLED=true to enable.")
            return []

        if not self.target_weights:
            logger.warning("Target weights empty. Set REBALANCE_TARGET_WEIGHTS in .env")
            return []

        logger.info("=" * 60)
        logger.info("Portfolio rebalancing started...")

        total_value = self.get_current_portfolio_value()
        if total_value <= 0:
            logger.warning("Total portfolio value is 0. Nothing to rebalance.")
            return []

        # Get current positions
        positions = self.storage.get_all_open_positions()
        current_qty: dict[str, float] = {p["ticker"]: p["quantity"] for p in positions}

        # Get current weights for logging
        current_weights = self.get_current_weights()
        logger.info(f"Current weights: {current_weights}")
        logger.info(f"Target weights: {self.target_weights}")

        results: list[dict] = []

        for ticker, target_weight in self.target_weights.items():
            if target_weight <= 0:
                continue

            price = self._get_latest_price(ticker)
            if not price:
                logger.warning(f"No price data for {ticker}, skipping.")
                continue

            target_qty = self._get_target_quantity(total_value, ticker, price)
            current = current_qty.get(ticker, 0)
            diff = target_qty - current

            if abs(diff) < 100:  # Ignore differences less than 1 lot
                logger.info(f"{ticker}: already balanced ({current} vs target {target_qty})")
                continue

            if diff > 0:
                result = self._execute_rebalance_buy(ticker, diff, price)
            else:
                result = self._execute_rebalance_sell(ticker, abs(diff), price)

            if result.get("status") == "ok":
                results.append(result)

        logger.info(f"Rebalancing complete. {len(results)} orders executed.")
        logger.info("=" * 60)
        return results

    def get_rebalance_status(self) -> dict:
        """Get current rebalance status for dashboard display."""
        current_weights = self.get_current_weights()
        return {
            "enabled": self.rebalance_enabled,
            "frequency": self.rebalance_frequency,
            "target_weights": self.target_weights,
            "current_weights": current_weights,
            "total_portfolio_value": self.get_current_portfolio_value(),
            "drift": {
                ticker: abs(current_weights.get(ticker, 0) - target)
                for ticker, target in self.target_weights.items()
            },
        }
