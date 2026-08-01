"""Replay Simulation — Point-in-time daily replay using full application pipeline.

Mengiterasi hari per hari selama N bulan terakhir, dan untuk setiap hari:
1. Memuat data OHLCV hanya sampai hari tersebut (point-in-time, no look-ahead)
2. Menghitung technical score (TechnicalAnalysisEngine)
3. Memuat skor macro/global/relationship/sentiment dari DB (pre-computed)
4. Menghitung conviction (DecisionEngine.compute_conviction + regime filter)
5. Memutuskan aksi BUY/HOLD/SELL/AVOID (DecisionEngine.decide_action)
6. Menghitung risk metrics: ATR, SL/TP, position sizing (RiskEngine logic)
7. Mengecek SL/TP/trailing stop untuk posisi yang ada
8. Mengeksekusi buy/sell dengan biaya realistik (CostModel IDX)
9. Mencatat equity harian (cash + nilai posisi)
10. Menyimpan orders, positions, equity snapshots, audit logs ke DB

Hasil tersimpan di DB dan dapat divisualisasikan via dashboard Playwright.

Penggunaan:
    ./venv/bin/python scripts/replay_simulation.py [--ticker BBCA.JK]
                                                    [--capital 10000000]
                                                    [--months 12]
                                                    [--clean]  # bersihkan data lama
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trading_system.analysis.technical import TechnicalAnalysisEngine
from trading_system.config import (
    DEFAULT_BENCHMARK,
    EXIT_CONVICTION_THRESHOLD,
    IDX_LOT_SIZE,
    TRADING_CAPITAL,
    round_to_tick,
)
from trading_system.data.storage import DataStorage
from trading_system.decision.engine import DEFAULT_WEIGHTS, DecisionEngine
from trading_system.risk.costs import CostModel, compute_atr, get_default_cost_model

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("replay_simulation")


class ReplaySimulation:
    """Point-in-time daily replay using the full application pipeline."""

    def __init__(
        self,
        ticker: str,
        capital: float = 10_000_000,
        months: int = 12,
        storage: DataStorage | None = None,
    ):
        self.ticker = ticker
        self.initial_capital = capital
        self.months = months
        self.storage = storage or DataStorage()
        self.technical = TechnicalAnalysisEngine()
        self.decision = DecisionEngine(self.storage)
        self.cost_model = get_default_cost_model()

        # Scores are pre-computed by precompute_scores.py and stored in DB
        # Replay just reads them — no re-computation needed (fast)
        self._scores_cache: dict[str, dict[str, float]] = {}
        self._regime_cache: dict[str, str] = {}

    def _load_scores_from_db(self, date: pd.Timestamp) -> dict[str, float]:
        """Load pre-computed scores from DB for this date — instant, no re-computation.

        Scores are pre-computed by precompute_scores.py and stored with as_of=date.
        Query: SELECT score FROM scores WHERE ticker=? AND engine=? AND as_of <= ? ORDER BY as_of DESC LIMIT 1
        """
        date_key = str(date.date())
        if date_key in self._scores_cache:
            return self._scores_cache[date_key]

        scores = {}
        engines = ["technical", "fundamental", "macro", "global", "relationship", "sentiment"]
        try:
            with self.storage._connect() as conn:
                for engine in engines:
                    row = conn.execute(
                        """SELECT score, breakdown FROM scores
                           WHERE ticker = ? AND engine = ? AND as_of <= ?
                           ORDER BY as_of DESC LIMIT 1""",
                        (self.ticker, engine, date_key),
                    ).fetchone()
                    if row:
                        scores[engine] = float(row[0])
                        # Extract regime from macro breakdown
                        if engine == "macro" and row[1]:
                            try:
                                breakdown = json.loads(row[1])
                                regime = breakdown.get("regime")
                                if regime:
                                    self._regime_cache[date_key] = regime
                            except Exception:
                                pass
                    else:
                        scores[engine] = 50.0
        except Exception as e:
            logger.warning(f"Failed to load scores for {date_key}: {e}")
            scores = {e: 50.0 for e in engines}

        self._scores_cache[date_key] = scores
        return scores

    def _get_macro_regime(self, date: pd.Timestamp | None = None) -> str | None:
        """Get macro regime for a specific date from pre-computed scores."""
        if date is None:
            # Fallback: use latest from DB
            df = self.storage.load_scores(self.ticker, engine="macro")
            if df.empty:
                return None
            try:
                import json
                breakdown = json.loads(df.iloc[0]["breakdown"])
                return breakdown.get("regime")
            except Exception:
                return None
        date_key = str(date.date())
        if date_key in self._regime_cache:
            return self._regime_cache[date_key]
        # Load scores which will populate regime cache
        self._load_scores_from_db(date)
        return self._regime_cache.get(date_key)

    def _compute_scores(self, df_up_to: pd.DataFrame, date: pd.Timestamp) -> dict[str, float]:
        """Load pre-computed scores from DB — instant, no re-computation."""
        return self._load_scores_from_db(date)

    def _compute_risk_from_df(self, df: pd.DataFrame, capital: float) -> dict:
        """Compute risk metrics from a filtered DataFrame (point-in-time)."""
        if df.empty or len(df) < 20:
            return {"stop_loss": 0, "take_profit": 0, "atr": 0, "risk_flags": [], "position_size": 0}

        close = df["close"]
        last_price = float(close.iloc[-1])
        atr_series = compute_atr(df, 14)
        atr = float(atr_series.iloc[-1]) if not atr_series.empty else 0.0
        if pd.isna(atr):
            atr = last_price * 0.02

        stop_distance = 1.5 * atr if atr > 0 else last_price * 0.05
        stop_loss = last_price - stop_distance
        take_profit = last_price + 2 * stop_distance

        # Position sizing: risk 1% of capital, stop = 1.5 ATR
        risk_amount = capital * 0.01
        position_value = risk_amount / (stop_distance / last_price) if stop_distance > 0 else 0
        position_size_pct = min(position_value / capital, 0.10)  # max 10%

        # Volatility
        vol = float(close.pct_change().rolling(20).std().iloc[-1] * np.sqrt(252)) if len(close) >= 20 else 0.2
        if pd.isna(vol):
            vol = 0.2

        # Max drawdown
        rolling_max = close.rolling(252, min_periods=1).max()
        drawdown = (close - rolling_max) / rolling_max
        max_drawdown = float(drawdown.min()) if not drawdown.empty else 0.0

        # Risk flags
        flags = []
        if vol > 0.5:
            flags.append("HIGH_VOLATILITY")
        if max_drawdown < -0.25:
            flags.append("SEVERE_DRAWDOWN")

        return {
            "last_price": round(last_price, 2),
            "atr": round(atr, 4),
            "stop_loss": round(stop_loss, 2),
            "take_profit": round(take_profit, 2),
            "position_size": round(position_size_pct, 4),
            "risk_flags": flags,
            "volatility": round(vol, 4),
            "max_drawdown": round(max_drawdown, 4),
        }

    def _execute_buy(
        self, date: pd.Timestamp, price: float, quantity: int,
        stop_loss: float, take_profit: float, capital: float,
    ) -> dict:
        """Execute a BUY order with realistic IDX costs."""
        # Apply buy cost (fee + levy + slippage)
        fill_price = round_to_tick(price * (1 + self.cost_model.buy_cost_pct()))
        order_value = quantity * fill_price
        fees = self.cost_model.compute_fees(order_value, action="buy")
        total_cost = order_value + fees["total"]

        # Save order to DB
        order_id = self.storage.save_order(
            ticker=self.ticker, order_type="BUY", quantity=quantity,
            price=fill_price, fee=fees["total"], trigger="REPLAY_SIGNAL",
        )

        # Save position to DB
        position_id = self.storage.save_position(
            ticker=self.ticker, quantity=quantity, avg_entry_price=fill_price,
            stop_loss=stop_loss, take_profit=take_profit,
        )

        # Audit log
        self.storage.audit("replay.buy", {
            "date": str(date), "order_id": order_id, "position_id": position_id,
            "ticker": self.ticker, "quantity": quantity, "price": fill_price,
            "fees": fees, "stop_loss": stop_loss, "take_profit": take_profit,
        })

        logger.info(f"  BUY {quantity} {self.ticker} @ Rp {fill_price:,.2f} | SL={stop_loss:,.2f} TP={take_profit:,.2f}")

        return {
            "action": "BUY", "date": str(date), "quantity": quantity,
            "price": fill_price, "fees": fees["total"],
            "order_id": order_id, "position_id": position_id,
            "capital_after": capital - total_cost,
        }

    def _execute_sell(
        self, date: pd.Timestamp, price: float, quantity: int,
        entry_price: float, trigger: str, position_id: int | None = None,
    ) -> dict:
        """Execute a SELL order with realistic IDX costs."""
        # Apply sell cost (fee + levy + slippage + tax)
        fill_price = round_to_tick(price * (1 - self.cost_model.sell_cost_pct()))
        order_value = quantity * fill_price
        fees = self.cost_model.compute_fees(order_value, action="sell")
        proceeds = order_value - fees["total"]
        realized_pnl = (fill_price - entry_price) * quantity

        # Save order to DB
        order_id = self.storage.save_order(
            ticker=self.ticker, order_type="SELL", quantity=quantity,
            price=fill_price, fee=fees["total"], trigger=f"REPLAY_{trigger}",
            realized_pnl=realized_pnl,
        )

        # Update position in DB
        if position_id:
            self.storage.update_position(
                position_id, status="CLOSED", quantity=0,
                current_price=fill_price, realized_pnl=realized_pnl,
            )

        # Audit log
        self.storage.audit("replay.sell", {
            "date": str(date), "order_id": order_id, "position_id": position_id,
            "ticker": self.ticker, "quantity": quantity, "price": fill_price,
            "fees": fees, "trigger": trigger, "realized_pnl": realized_pnl,
        })

        logger.info(
            f"  SELL {quantity} {self.ticker} @ Rp {fill_price:,.2f} | "
            f"PnL={realized_pnl:,.0f} ({trigger})"
        )

        return {
            "action": "SELL", "date": str(date), "quantity": quantity,
            "price": fill_price, "fees": fees["total"],
            "realized_pnl": realized_pnl, "trigger": trigger,
            "order_id": order_id, "proceeds": proceeds,
        }

    def _check_sl_tp(
        self, date: pd.Timestamp, current_price: float, position: dict,
    ) -> str | None:
        """Check if stop-loss, take-profit, or trailing stop is triggered."""
        entry = position["entry_price"]
        sl = position["stop_loss"]
        tp = position["take_profit"]
        highest = position.get("highest_price", entry)

        # Update highest price
        if current_price > highest:
            position["highest_price"] = current_price

        # Stop Loss
        if sl and current_price <= sl:
            return "STOP_LOSS"

        # Take Profit
        if tp and current_price >= tp:
            return "TAKE_PROFIT"

        # Trailing Stop (5% from highest)
        trail_pct = 0.05
        if highest > entry:
            trail_level = highest * (1 - trail_pct)
            if current_price <= trail_level and current_price < highest:
                return "TRAILING_STOP"

        return None

    def _clean_old_data(self):
        """Clean old replay data from DB."""
        logger.info("Cleaning old replay data...")
        with self.storage._connect() as conn:
            conn.execute("DELETE FROM orders WHERE trigger LIKE 'REPLAY_%'")
            conn.execute("DELETE FROM positions WHERE ticker = ?", (self.ticker,))
            conn.execute("DELETE FROM equity_snapshots")
            conn.execute("DELETE FROM audit_log WHERE event_type LIKE 'replay.%'")
        logger.info("Old replay data cleaned.")

    def run(self, clean: bool = False) -> dict:
        """Run the full replay simulation."""
        if clean:
            self._clean_old_data()

        # Load full OHLCV data
        full_df = self.storage.load_ohlcv(self.ticker)
        if full_df.empty:
            return {"status": "error", "message": f"No OHLCV data for {self.ticker}"}

        # Calculate replay period
        end_date = full_df.index[-1]
        start_date = end_date - timedelta(days=self.months * 30)
        replay_days = full_df[full_df.index >= start_date].index

        logger.info("=" * 70)
        logger.info(f"REPLAY SIMULATION: {self.ticker}")
        logger.info(f"  Modal awal   : Rp {self.initial_capital:,.0f}")
        logger.info(f"  Periode      : {replay_days[0].date()} → {replay_days[-1].date()} ({len(replay_days)} hari)")
        logger.info(f"  Macro regime : {self._get_macro_regime()}")
        logger.info("=" * 70)

        # State
        cash = self.initial_capital
        position = None  # {position_id, quantity, entry_price, stop_loss, take_profit, highest_price}
        equity_curve = []
        trades = []
        daily_records = []

        # Get macro regime for conviction computation (updated per-day inside loop)
        macro_regime = self._get_macro_regime()

        # Get AI-optimized weights
        weights = self.decision.ai_learning.get_factor_weights(self.ticker, macro_regime)
        weights = self.decision._redistribute_weights(weights, self.ticker)
        logger.info(f"  Weights      : {weights}")

        for i, date in enumerate(replay_days):
            # Point-in-time: filter data up to this date
            df_up_to = full_df[full_df.index <= date].copy()

            if len(df_up_to) < 50:
                continue  # Need at least 50 bars for MA50

            current_price = float(df_up_to["close"].iloc[-1])

            # 1. Compute scores (point-in-time) — ALL engines run fresh each day
            scores = self._compute_scores(df_up_to, date)

            # Update macro regime from today's computation
            date_key = str(date.date())
            if date_key in self._macro_cache:
                macro_regime = self._macro_cache[date_key][1].get("regime", macro_regime)

            # 2. Apply regime filter
            adjusted_scores = self.decision.apply_regime_filter(scores, macro_regime)

            # 3. Compute conviction
            conviction = self.decision.compute_conviction(adjusted_scores, weights)

            # 4. Compute risk metrics (point-in-time)
            risk = self._compute_risk_from_df(df_up_to, cash)

            # 5. Check SL/TP for existing position
            sl_tp_trigger = None
            if position:
                sl_tp_trigger = self._check_sl_tp(date, current_price, position)

            # 6. Decide action
            has_position = position is not None
            if sl_tp_trigger:
                action = "SELL"
                sell_trigger = sl_tp_trigger
            else:
                action = self.decision.decide_action(
                    conviction, risk["risk_flags"], has_position=has_position,
                )
                sell_trigger = "SIGNAL"

            # 7. Execute trades
            trade_executed = None

            # SELL: close existing position
            if action == "SELL" and position:
                trade_executed = self._execute_sell(
                    date, current_price, position["quantity"],
                    position["entry_price"], sell_trigger, position["position_id"],
                )
                cash += trade_executed["proceeds"]
                trades.append({
                    **trade_executed,
                    "conviction": conviction,
                    "scores": adjusted_scores,
                })
                position = None

            # BUY: open new position
            elif action == "BUY" and not position:
                # Calculate position size (shares, rounded to lot)
                position_value = risk["position_size"] * cash
                max_shares = int(position_value / risk["last_price"])
                quantity = (max_shares // IDX_LOT_SIZE) * IDX_LOT_SIZE

                if quantity > 0:
                    # Check if we have enough cash (with fees)
                    fill_price_est = round_to_tick(current_price * (1 + self.cost_model.buy_cost_pct()))
                    total_cost = quantity * fill_price_est * (1 + self.cost_model.buy_cost_pct())
                    if total_cost <= cash:
                        trade_executed = self._execute_buy(
                            date, current_price, quantity,
                            risk["stop_loss"], risk["take_profit"], cash,
                        )
                        cash = trade_executed["capital_after"]
                        position = {
                            "position_id": trade_executed["position_id"],
                            "quantity": quantity,
                            "entry_price": trade_executed["price"],
                            "stop_loss": risk["stop_loss"],
                            "take_profit": risk["take_profit"],
                            "highest_price": trade_executed["price"],
                        }
                        trades.append({
                            **trade_executed,
                            "conviction": conviction,
                            "scores": adjusted_scores,
                        })

            # 8. Track equity
            positions_value = position["quantity"] * current_price if position else 0
            equity = cash + positions_value
            unrealized_pnl = (current_price - position["entry_price"]) * position["quantity"] if position else 0
            total_return_pct = (equity - self.initial_capital) / self.initial_capital * 100

            equity_curve.append({
                "date": str(date.date()),
                "equity": round(equity, 2),
                "cash": round(cash, 2),
                "positions_value": round(positions_value, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "total_return_pct": round(total_return_pct, 2),
            })

            # 9. Save equity snapshot to DB (for dashboard performance page)
            self.storage.save_equity_snapshot(
                equity=equity, cash=cash, positions_value=positions_value,
                realized_pnl=sum(t.get("realized_pnl", 0) for t in trades if t["action"] == "SELL"),
                unrealized_pnl=unrealized_pnl,
                total_return_pct=total_return_pct,
            )

            # 10. Update position in DB (current price, unrealized PnL)
            if position:
                self.storage.update_position(
                    position["position_id"],
                    current_price=current_price,
                    unrealized_pnl=unrealized_pnl,
                    return_pct=(current_price / position["entry_price"] - 1) * 100,
                    highest_price_since_entry=position["highest_price"],
                )

            # Daily record — full detail for visualization
            daily_records.append({
                "date": str(date.date()),
                "day": i + 1,
                "price": round(current_price, 2),
                "action": action,
                "sell_trigger": sell_trigger if action == "SELL" else None,
                "conviction": round(conviction, 2),
                "scores": {k: round(v, 2) for k, v in adjusted_scores.items()},
                "weights": {k: round(v, 4) for k, v in weights.items()},
                "regime": macro_regime,
                "risk": {
                    "stop_loss": risk["stop_loss"],
                    "take_profit": risk["take_profit"],
                    "atr": risk["atr"],
                    "position_size": risk["position_size"],
                    "volatility": risk["volatility"],
                    "max_drawdown": risk["max_drawdown"],
                    "risk_flags": risk["risk_flags"],
                    "last_price": risk["last_price"],
                },
                "portfolio": {
                    "cash": round(cash, 2),
                    "positions_value": round(positions_value, 2),
                    "equity": round(equity, 2),
                    "unrealized_pnl": round(unrealized_pnl, 2),
                    "total_return_pct": round(total_return_pct, 2),
                    "has_position": position is not None,
                    "position_qty": position["quantity"] if position else 0,
                    "position_entry": position["entry_price"] if position else None,
                    "position_highest": position["highest_price"] if position else None,
                },
                "trade": trade_executed if trade_executed else None,
            })

            # Log progress every 20 days
            if (i + 1) % 20 == 0 or i == 0 or i == len(replay_days) - 1:
                logger.info(
                    f"  [{date.date()}] Day {i+1}/{len(replay_days)} | "
                    f"Price={current_price:,.2f} | Action={action} | "
                    f"Conviction={conviction:.1f} | Equity={equity:,.0f} | "
                    f"Return={total_return_pct:+.2f}%"
                )

        # Close any remaining position at the last price
        if position:
            last_price = float(full_df["close"].iloc[-1])
            trade_executed = self._execute_sell(
                replay_days[-1], last_price, position["quantity"],
                position["entry_price"], "REPLAY_END", position["position_id"],
            )
            cash += trade_executed["proceeds"]
            trades.append({
                **trade_executed,
                "conviction": conviction,
                "scores": adjusted_scores,
            })
            position = None
            logger.info(f"  Closed remaining position at end of replay")

        # Final results
        final_equity = cash
        total_return = (final_equity - self.initial_capital) / self.initial_capital * 100
        n_buys = sum(1 for t in trades if t["action"] == "BUY")
        n_sells = sum(1 for t in trades if t["action"] == "SELL")
        n_sl = sum(1 for t in trades if t.get("trigger") == "STOP_LOSS")
        n_tp = sum(1 for t in trades if t.get("trigger") == "TAKE_PROFIT")
        n_ts = sum(1 for t in trades if t.get("trigger") == "TRAILING_STOP")
        n_signal = sum(1 for t in trades if t.get("trigger") == "SIGNAL")
        total_fees = sum(t.get("fees", 0) for t in trades)
        total_realized_pnl = sum(t.get("realized_pnl", 0) for t in trades if t["action"] == "SELL")

        # Compute performance metrics
        equity_series = pd.Series([e["equity"] for e in equity_curve])
        returns = equity_series.pct_change().dropna()
        sharpe = float(returns.mean() / returns.std() * np.sqrt(252)) if len(returns) > 1 and returns.std() > 0 else 0
        rolling_max = equity_series.cummax()
        drawdown = (equity_series - rolling_max) / rolling_max
        max_drawdown = float(drawdown.min()) if not drawdown.empty else 0

        results = {
            "status": "ok",
            "ticker": self.ticker,
            "initial_capital": self.initial_capital,
            "final_equity": round(final_equity, 2),
            "total_return_pct": round(total_return, 2),
            "total_realized_pnl": round(total_realized_pnl, 2),
            "total_fees": round(total_fees, 2),
            "sharpe_ratio": round(sharpe, 4),
            "max_drawdown_pct": round(abs(max_drawdown) * 100, 2),
            "n_trading_days": len(replay_days),
            "n_buys": n_buys,
            "n_sells": n_sells,
            "n_stop_loss": n_sl,
            "n_take_profit": n_tp,
            "n_trailing_stop": n_ts,
            "n_signal_sell": n_signal,
            "trades": trades,
            "equity_curve": equity_curve,
            "daily_records": daily_records,
        }

        logger.info("=" * 70)
        logger.info("REPLAY SIMULATION COMPLETE")
        logger.info("=" * 70)
        logger.info(f"  Final Equity    : Rp {final_equity:,.2f}")
        logger.info(f"  Total Return    : {total_return:+.2f}%")
        logger.info(f"  Realized PnL    : Rp {total_realized_pnl:,.2f}")
        logger.info(f"  Total Fees      : Rp {total_fees:,.2f}")
        logger.info(f"  Sharpe Ratio    : {sharpe:.4f}")
        logger.info(f"  Max Drawdown    : {abs(max_drawdown)*100:.2f}%")
        logger.info(f"  Trades          : {n_buys} buys, {n_sells} sells")
        logger.info(f"    Stop Loss     : {n_sl}")
        logger.info(f"    Take Profit   : {n_tp}")
        logger.info(f"    Trailing Stop : {n_ts}")
        logger.info(f"    Signal SELL   : {n_signal}")
        logger.info("=" * 70)

        return results


def main():
    parser = argparse.ArgumentParser(description="Replay simulation using full app pipeline")
    parser.add_argument("--ticker", default="BBCA.JK", help="Ticker symbol")
    parser.add_argument("--capital", type=float, default=10_000_000, help="Initial capital (IDR)")
    parser.add_argument("--months", type=int, default=12, help="Replay period in months")
    parser.add_argument("--clean", action="store_true", help="Clean old replay data before running")
    args = parser.parse_args()

    sim = ReplaySimulation(
        ticker=args.ticker,
        capital=args.capital,
        months=args.months,
    )
    results = sim.run(clean=args.clean)

    if results["status"] != "ok":
        print(f"Error: {results.get('message')}")
        sys.exit(1)

    # Save results to JSON for the Playwright visualization
    results_file = Path(__file__).parent / "replay_results.json"
    # Convert non-serializable items
    serializable = {k: v for k, v in results.items() if k not in ("trades", "equity_curve", "daily_records")}
    serializable["trades"] = results["trades"]
    serializable["equity_curve"] = results["equity_curve"]
    serializable["daily_records_count"] = len(results["daily_records"])

    import json
    with open(results_file, "w") as f:
        json.dump(serializable, f, indent=2, default=str)
    logger.info(f"Results saved to {results_file}")


if __name__ == "__main__":
    main()
