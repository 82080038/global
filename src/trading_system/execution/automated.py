"""Automated Execution Engine — Robot Trader.

Membaca sinyal dari Decision Engine, menghitung position sizing dari Risk Engine,
mengeksekusi order otomatis, dan memantau Stop-Loss / Take-Profit / Trailing Stop.

Gunakan AUTO_TRADE_ENABLED=true di .env untuk mengaktifkan eksekusi nyata.
Default false = mode monitoring (hanya log, tidak eksekusi).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import UTC

from trading_system.config import TRADING_CAPITAL
from trading_system.data.storage import DataStorage
from trading_system.decision.engine import DecisionEngine
from trading_system.execution import get_execution_engine
from trading_system.execution.engine import ExecutionEngine
from trading_system.risk.costs import get_default_cost_model, get_latest_atr
from trading_system.risk.engine import RiskEngine

logger = logging.getLogger(__name__)


class AutomatedExecutionEngine:
    """Automated trading engine that reads signals and executes orders.

    Modes:
    - AUTO_TRADE_ENABLED=false (default): Monitor only, log signals, no execution.
    - AUTO_TRADE_ENABLED=true: Execute BUY/SELL orders automatically.
    """

    name = "automated_execution"

    def __init__(self, storage: DataStorage | None = None):
        self.storage = storage or DataStorage()
        self.decision = DecisionEngine(self.storage)
        self.risk = RiskEngine(self.storage)
        self.execution = ExecutionEngine()  # Keep for cost calculations
        self.trading_executor = get_execution_engine(storage)  # New shared interface
        self.auto_trade_enabled = os.getenv("AUTO_TRADE_ENABLED", "false").lower() == "true"
        self.capital = TRADING_CAPITAL
        self.risk_per_trade = float(os.getenv("RISK_PER_TRADE", "0.01"))
        self.daily_loss_limit = float(os.getenv("DAILY_LOSS_LIMIT", "0"))

        if not self.auto_trade_enabled:
            logger.warning("AUTO_TRADE_ENABLED=false. Eksekusi otomatis DINONAKTIFKAN (mode monitoring).")

    def _get_latest_price(self, ticker: str) -> float | None:
        """Get latest close price from OHLCV data."""
        df = self.storage.load_ohlcv(ticker)
        if df.empty:
            return None
        return float(df["close"].iloc[-1])

    def _get_atr(self, ticker: str) -> float:
        """Get latest ATR(14) via consolidated costs.py (P2-4)."""
        df = self.storage.load_ohlcv(ticker)
        return get_latest_atr(df, 14)

    def _compute_position_size(self, ticker: str, price: float) -> int:
        """Compute position size based on ATR and risk per trade.

        Returns quantity in shares (rounded to lot of 100).
        """
        atr = self._get_atr(ticker)
        risk_amount = self.capital * self.risk_per_trade

        if atr > 0:
            stop_distance = 1.5 * atr
            quantity = risk_amount / stop_distance
        else:
            # Fallback: 1% of capital divided by price
            quantity = (self.capital * 0.01) / price

        # Round to lot (100 shares for IDX)
        quantity = max(100, int(quantity // 100) * 100)

        # Cap at 10% of capital
        max_shares = (self.capital * 0.10) / price
        quantity = min(quantity, int(max_shares // 100) * 100)

        return max(quantity, 0)

    def _execute_buy(self, ticker: str, quantity: int, price: float, trigger: str = "SIGNAL") -> dict:
        """Execute a BUY order and create a position."""
        if quantity <= 0:
            return {"status": "skipped", "reason": "quantity is 0"}

        order_value = quantity * price
        cost_model = get_default_cost_model()
        fee = order_value * (cost_model.buy_fee + cost_model.levy)

        # Compute stop loss / take profit from risk engine
        risk_data = self.risk.analyze(ticker)
        stop_loss = risk_data.get("stop_loss", price * 0.95)
        take_profit = risk_data.get("take_profit", price * 1.10)

        # Save order
        order_id = self.storage.save_order(
            ticker=ticker, order_type="BUY", quantity=quantity, price=price,
            fee=fee, trigger=trigger,
        )

        # Create position
        position_id = self.storage.save_position(
            ticker=ticker, quantity=quantity, avg_entry_price=price,
            stop_loss=stop_loss, take_profit=take_profit,
        )

        # Audit
        self.storage.audit("execution.buy", {
            "order_id": order_id, "position_id": position_id,
            "ticker": ticker, "quantity": quantity, "price": price,
            "fee": fee, "trigger": trigger,
        })

        logger.info(f"BUY {quantity} {ticker} @ Rp {price:,.2f} (fee: {fee:,.0f})")

        return {
            "status": "ok", "action": "BUY", "ticker": ticker,
            "quantity": quantity, "price": price, "fee": fee,
            "stop_loss": stop_loss, "take_profit": take_profit,
            "order_id": order_id, "position_id": position_id,
        }

    def _execute_sell(self, ticker: str, quantity: int, price: float,
                      trigger: str = "SIGNAL", position: dict | None = None) -> dict:
        """Execute a SELL order and close/update position."""
        if quantity <= 0:
            return {"status": "skipped", "reason": "quantity is 0"}

        order_value = quantity * price
        cost_model = get_default_cost_model()
        fee = order_value * (cost_model.sell_fee + cost_model.levy + 0.001)  # sell fee + levy + tax

        # Compute realized PnL from the actual position entry price BEFORE saving
        # the order, so it can be persisted directly on the order row instead of
        # being re-estimated later from the average of all historical BUYs
        # (§3.4 SARAN_PENGEMBANGAN.md).
        realized_pnl = 0.0
        if position:
            entry = position.get("avg_entry_price", 0)
            realized_pnl = (price - entry) * quantity

        # Save order
        order_id = self.storage.save_order(
            ticker=ticker, order_type="SELL", quantity=quantity, price=price,
            fee=fee, trigger=trigger, realized_pnl=realized_pnl,
        )

        # Update position
        if position:
            remaining = position.get("quantity", 0) - quantity

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

        # Audit
        self.storage.audit("execution.sell", {
            "order_id": order_id, "ticker": ticker,
            "quantity": quantity, "price": price,
            "fee": fee, "trigger": trigger,
            "realized_pnl": realized_pnl,
        })

        logger.info(f"SELL {quantity} {ticker} @ Rp {price:,.2f} (PnL: {realized_pnl:,.0f})")


        return {
            "status": "ok", "action": "SELL", "ticker": ticker,
            "quantity": quantity, "price": price, "fee": fee,
            "realized_pnl": realized_pnl,
            "order_id": order_id,
        }

    def check_stop_loss_take_profit(self, ticker: str) -> dict | None:
        """Check if open position for ticker hits SL/TP/Trailing Stop. Execute sell if triggered."""
        position = self.storage.get_open_position(ticker)
        if not position:
            return None

        current_price = self._get_latest_price(ticker)
        if not current_price:
            return None

        entry = position.get("avg_entry_price", 0)
        qty = position.get("quantity", 0)
        unrealized = (current_price - entry) * qty
        return_pct = (current_price / entry - 1) * 100 if entry > 0 else 0

        # Update position metrics
        highest = position.get("highest_price_since_entry", entry)
        if current_price > highest:
            highest = current_price

        self.storage.update_position(
            position["id"], current_price=current_price,
            unrealized_pnl=unrealized, return_pct=return_pct,
            highest_price_since_entry=highest,
        )

        # Check Stop Loss
        sl = position.get("stop_loss")
        if sl and current_price <= sl:
            logger.info(f"STOP LOSS TRIGGERED: {ticker} @ {current_price:.2f} <= {sl:.2f}")
            return self._execute_sell(ticker, int(qty), current_price,
                                      trigger="STOP_LOSS", position=position)

        # Check Take Profit
        tp = position.get("take_profit")
        if tp and current_price >= tp:
            logger.info(f"TAKE PROFIT TRIGGERED: {ticker} @ {current_price:.2f} >= {tp:.2f}")
            return self._execute_sell(ticker, int(qty), current_price,
                                      trigger="TAKE_PROFIT", position=position)

        # Check Trailing Stop
        trail_pct = position.get("trailing_stop_pct", 0.05)
        if trail_pct and highest > entry:
            trail_level = highest * (1 - trail_pct)
            if current_price <= trail_level and current_price < highest:
                logger.info(f"TRAILING STOP TRIGGERED: {ticker} @ {current_price:.2f} <= {trail_level:.2f}")
                return self._execute_sell(ticker, int(qty), current_price,
                                          trigger="TRAILING_STOP", position=position)

        return None

    def process_signal(self, ticker: str) -> dict:
        """Process a single ticker: check signals and execute if needed."""
        # 1. Check SL/TP for existing positions
        sl_tp_result = self.check_stop_loss_take_profit(ticker)
        if sl_tp_result:
            return sl_tp_result

        # 2. If auto-trade is disabled, just log
        if not self.auto_trade_enabled:
            # Still get recommendation for monitoring
            rec = self.decision.recommend(ticker, capital=self.capital)
            if rec.get("status") == "ok":
                action = rec["recommendation"]["action"]
                if action in ("BUY", "SELL"):
                    logger.info(f"[MONITOR] {ticker}: Signal {action} (auto-trade disabled, no execution)")
            return {"status": "monitoring", "ticker": ticker, "auto_trade": False}

        # 3. Get recommendation from Decision Engine
        rec = self.decision.recommend(ticker, capital=self.capital)
        if rec.get("status") != "ok":
            return {"status": "skipped", "ticker": ticker, "reason": "no recommendation"}

        action = rec["recommendation"]["action"]

        # 4. Check existing position
        position = self.storage.get_open_position(ticker)
        price = self._get_latest_price(ticker)
        if not price:
            return {"status": "skipped", "ticker": ticker, "reason": "no price data"}

        # 5. Execute based on signal
        if action == "BUY" and not position:
            quantity = self._compute_position_size(ticker, price)
            if quantity > 0:
                return self._execute_buy(ticker, quantity, price, trigger="SIGNAL")
            return {"status": "skipped", "ticker": ticker, "reason": "quantity is 0"}

        elif action == "SELL" and position:
            qty = int(position.get("quantity", 0))
            if qty > 0:
                return self._execute_sell(ticker, qty, price,
                                          trigger="SIGNAL", position=position)

        return {"status": "no_action", "ticker": ticker, "action": action}

    def _check_daily_loss_limit(self) -> bool:
        """Check if daily loss exceeds limit. Returns True if trading should STOP.

        Sums the `realized_pnl` column persisted on today's SELL orders (recorded
        at execution time from the actual position entry price — see
        `_execute_sell`) instead of re-estimating PnL from the average of ALL
        historical BUY prices for the ticker, which could be wildly inaccurate
        (§3.4 SARAN_PENGEMBANGAN.md).

        The halt flag is persisted in `system_state` so that once triggered, it
        stays in effect for the rest of the day even across separate scheduler
        cycles/process restarts — previously the circuit breaker only halted the
        single cycle where the limit was crossed.
        """
        if self.daily_loss_limit <= 0:
            return False  # No limit set

        from datetime import datetime
        today = datetime.now(UTC).date().isoformat()

        # Already halted today? (persisted from a previous cycle)
        halted_date = self.storage.get_state("execution_halted_date")
        if halted_date == today:
            return True

        orders = self.storage.get_orders(limit=10000)
        today_sells = [
            o for o in orders
            if o.get("order_type") == "SELL"
            and o.get("created_at", "").startswith(today)
        ]

        if not today_sells:
            return False

        total_pnl_today = sum(float(o.get("realized_pnl") or 0) for o in today_sells)

        if total_pnl_today < -self.daily_loss_limit:
            logger.warning(
                f"DAILY LOSS LIMIT HIT! Loss: Rp {abs(total_pnl_today):,.2f} "
                f"> Limit: Rp {self.daily_loss_limit:,.2f}"
            )
            # Persist halt flag so the rest of TODAY's cycles stay halted too.
            self.storage.set_state("execution_halted_date", today)
            return True  # STOP trading

        return False

    def run_once(self, tickers: list[str] | None = None) -> list[dict]:
        """Run one full cycle: scan all tickers for signals and SL/TP.

        Args:
            tickers: List of tickers to process. If None, loads from DB.

        Returns:
            List of execution results.
        """
        logger.info("=" * 60)
        logger.info("Automated execution cycle started...")

        # Circuit breaker: check daily loss limit first (safety priority)
        if self._check_daily_loss_limit():
            logger.error("Daily Loss Limit reached. Execution halted for today.")
            return [{"status": "circuit_breaker", "reason": "daily_loss_limit"}]

        # Market status check: skip if market is closed
        from trading_system.utils.market_status import get_market_status

        mkt = get_market_status(self.storage)
        if not mkt["is_open"]:
            logger.info(
                "Market closed (session=%s, holiday=%s). Skipping execution cycle.",
                mkt["session"],
                mkt.get("holiday_name") or "N/A",
            )
            return [{"status": "market_closed", "session": mkt["session"], "next_open": mkt.get("next_open")}]

        if tickers is None:
            tickers = self.storage.list_active_equity_tickers()

        if not tickers:
            logger.warning("No tickers found.")
            return []

        logger.info(f"Processing {len(tickers)} tickers... (auto_trade={self.auto_trade_enabled})")

        results = []
        for ticker in tickers:
            try:
                result = self.process_signal(ticker)
                if result.get("status") not in ("no_action", "monitoring", "skipped"):
                    results.append(result)
            except Exception as e:
                logger.error(f"Error processing {ticker}: {e}")
                results.append({"status": "error", "ticker": ticker, "error": str(e)})

        logger.info(f"Cycle complete. {len(results)} actions taken.")
        logger.info("=" * 60)
        return results

    def start_scheduler(self, interval_minutes: int = 15, tickers: list[str] | None = None):
        """Start the automated execution scheduler.

        In trading mode (market open): runs every `interval_minutes` for signal execution.
        In maintenance mode (market closed): run_once skips execution automatically,
        but still logs market status for visibility.

        Args:
            interval_minutes: Check interval in minutes (default 15 during trading hours).
            tickers: List of tickers to monitor. If None, loads from DB.
        """
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.interval import IntervalTrigger
        except ImportError:
            logger.error("apscheduler not installed. Install with: pip install apscheduler")
            return

        from trading_system.utils.market_status import get_market_status

        mkt = get_market_status(self.storage)
        if mkt["mode"] == "trading":
            logger.info("Scheduler starting in TRADING mode (market open). Interval: %d min.", interval_minutes)
        else:
            logger.info(
                "Scheduler starting in MAINTENANCE mode (market %s). Execution cycles will be skipped.",
                mkt["session"],
            )

        scheduler = BackgroundScheduler()
        scheduler.add_job(
            self.run_once,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id="auto_execution",
            replace_existing=True,
            kwargs={"tickers": tickers},
        )

        # Add rebalancing job if enabled
        try:
            from trading_system.portfolio.rebalancer import PortfolioRebalancer
            rebalancer = PortfolioRebalancer(storage=self.storage)
            if rebalancer.rebalance_enabled:
                freq = rebalancer.rebalance_frequency
                if freq == "daily":
                    rebalance_trigger = IntervalTrigger(days=1)
                elif freq == "weekly":
                    rebalance_trigger = IntervalTrigger(days=7)
                else:  # monthly
                    rebalance_trigger = IntervalTrigger(days=30)
                scheduler.add_job(
                    rebalancer.run_rebalance,
                    trigger=rebalance_trigger,
                    id="rebalance",
                    replace_existing=True,
                )
                logger.info(f"Rebalancing scheduled: {freq}")
        except Exception as e:
            logger.warning(f"Could not add rebalancing job: {e}")

        scheduler.start()
        logger.info(f"Scheduler started. Interval: {interval_minutes} minutes.")

        # Run once immediately
        self.run_once(tickers)

        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user.")
            scheduler.shutdown()


# Entry point for CLI
if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    engine = AutomatedExecutionEngine()

    if "--once" in sys.argv:
        engine.run_once()
    else:
        engine.start_scheduler()
