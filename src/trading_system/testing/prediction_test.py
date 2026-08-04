"""Prediction Testing Harness — walk-forward validation of trading system predictions.

Menguji apakah flow, logic, dan engine sistem trading menghasilkan prediksi yang benar.
Untuk setiap tanggal T dalam range:
  1. Load OHLCV up to T (PIT-safe, tidak bocor ke masa depan)
  2. Compute technical indicators pada slice data tersebut
  3. Generate prediction (BUY/HOLD/SELL) berdasarkan strategy
  4. Fast-forward ke T+horizon, dapat actual return
  5. Compare: prediction correct?

Output: accuracy, hit rate, confusion matrix, per-date results, equity curve.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

import numpy as np
import pandas as pd

from trading_system.data.storage import DataStorage


@dataclass
class TestConfig:
    """Konfigurasi test run."""
    ticker: str
    start_date: str  # YYYY-MM-DD — tanggal mulai test window
    end_date: str  # YYYY-MM-DD — tanggal akhir test window
    horizon: int = 5  # hari ke depan untuk evaluasi actual return
    step: int = 1  # interval antar test point (hari trading)
    strategy: str = "technical_rsi_sma"  # strategy name
    params: dict = field(default_factory=dict)
    min_history: int = 200  # minimum bar historis sebelum tanggal T


@dataclass
class TestResult:
    """Hasil satu test point (satu tanggal T)."""
    date: str  # tanggal T
    prediction: str  # BUY / HOLD / SELL
    conviction: float  # 0-100
    actual_return: float  # return T -> T+horizon (persen)
    actual_direction: str  # UP / DOWN / FLAT
    correct: bool  # prediction match actual?
    price_at_t: float
    price_at_t_plus: float
    indicators: dict  # snapshot indikator saat prediksi


@dataclass
class TestSummary:
    """Summary agregat dari test run."""
    ticker: str
    strategy: str
    total_predictions: int
    correct_predictions: int
    accuracy: float  # %
    buy_count: int
    sell_count: int
    hold_count: int
    buy_accuracy: float
    sell_accuracy: float
    hold_accuracy: float
    confusion_matrix: dict  # {predicted: {actual: count}}
    mean_actual_return: float
    sharpe_of_predictions: float
    equity_curve: list  # [{date, equity}] — simulated equity kalau ikuti prediksi


# --- Strategy functions ---

def strategy_technical_rsi_sma(indicators: pd.DataFrame, params: dict) -> tuple[str, float]:
    """Strategy: RSI + SMA crossover.

    BUY jika RSI < oversold_threshold (oversold) DAN close > SMA50 (uptrend).
    SELL jika RSI > overbought_threshold (overbought) DAN close < SMA50 (downtrend).
    HOLD otherwise.

    Returns (action, conviction).
    """
    if indicators.empty:
        return "HOLD", 0.0
    last = indicators.iloc[-1]
    rsi = last.get("rsi")
    close = last.get("close")
    sma50 = last.get("ma_50")
    sma200 = last.get("sma_200")

    if rsi is None or close is None or sma50 is None or pd.isna(rsi) or pd.isna(sma50):
        return "HOLD", 0.0

    oversold = params.get("oversold", 35)
    overbought = params.get("overbought", 70)

    # Conviction berdasarkan kekuatan sinyal
    conviction = 50.0

    if rsi < oversold and close > sma50:
        # Oversold di uptrend → BUY
        conviction = 70 + (oversold - rsi)  # makin oversold, makin tinggi conviction
        return "BUY", min(conviction, 100)
    elif rsi > overbought and close < sma50:
        # Overbought di downtrend → SELL
        conviction = 70 + (rsi - overbought)
        return "SELL", min(conviction, 100)
    elif close > sma50 and sma200 is not None and not pd.isna(sma200) and close > sma200:
        # Uptrend kuat tapi tidak oversold → HOLD bullish
        conviction = 55
        return "HOLD", conviction
    elif close < sma50 and sma200 is not None and not pd.isna(sma200) and close < sma200:
        # Downtrend → HOLD bearish
        conviction = 45
        return "HOLD", conviction
    else:
        return "HOLD", 50.0


def strategy_momentum(indicators: pd.DataFrame, params: dict) -> tuple[str, float]:
    """Strategy: momentum berdasarkan MACD + ADX.

    BUY jika MACD hist > 0 DAN ADX > 25 (strong uptrend momentum).
    SELL jika MACD hist < 0 DAN ADX > 25 (strong downtrend momentum).
    HOLD otherwise.
    """
    if indicators.empty:
        return "HOLD", 0.0
    last = indicators.iloc[-1]
    macd = last.get("macd")
    macd_signal = last.get("macd_signal")
    adx = last.get("adx")

    if macd is None or adx is None or pd.isna(macd) or pd.isna(adx):
        return "HOLD", 0.0

    macd_hist = macd - (macd_signal or 0) if macd_signal and not pd.isna(macd_signal) else 0
    min_adx = params.get("min_adx", 25)

    if macd_hist > 0 and adx > min_adx:
        conviction = 65 + min((adx - min_adx) * 0.5, 30)
        return "BUY", min(conviction, 100)
    elif macd_hist < 0 and adx > min_adx:
        conviction = 65 + min((adx - min_adx) * 0.5, 30)
        return "SELL", min(conviction, 100)
    else:
        return "HOLD", 50.0


def strategy_mean_reversion(indicators: pd.DataFrame, params: dict) -> tuple[str, float]:
    """Strategy: mean reversion berdasarkan Bollinger Bands.

    BUY jika close < bb_lower (oversold, bounce expected).
    SELL jika close > bb_upper (overbought, reversion expected).
    HOLD jika di tengah band.
    """
    if indicators.empty:
        return "HOLD", 0.0
    last = indicators.iloc[-1]
    close = last.get("close")
    bb_lower = last.get("bb_lower")
    bb_upper = last.get("bb_upper")
    bb_mid = last.get("bb_mid") or last.get("ma_20")

    if any(v is None or pd.isna(v) for v in [close, bb_lower, bb_upper]):
        return "HOLD", 0.0

    if close < bb_lower:
        return "BUY", 72
    elif close > bb_upper:
        return "SELL", 72
    else:
        # Distance dari mid
        if bb_mid and not pd.isna(bb_mid):
            pct_pos = (close - bb_mid) / (bb_upper - bb_lower) * 2  # -1 to 1
            conviction = 50 + abs(pct_pos) * 10
        else:
            conviction = 50
        return "HOLD", conviction


STRATEGIES: dict[str, Callable[[pd.DataFrame, dict], tuple[str, float]]] = {
    "technical_rsi_sma": strategy_technical_rsi_sma,
    "momentum": strategy_momentum,
    "mean_reversion": strategy_mean_reversion,
}


class PredictionTestHarness:
    """Walk-forward prediction accuracy test harness.

    Untuk setiap tanggal T dalam range, jalankan strategy pada data up-to-T,
    generate prediction, evaluasi terhadap actual return T+horizon.
    """

    def __init__(self, storage: DataStorage | None = None):
        self.storage = storage or DataStorage()

    def run(
        self,
        config: TestConfig,
        progress_callback: Callable[[dict], None] | None = None,
    ) -> dict[str, Any]:
        """Run prediction test dan return summary + per-date results.

        Args:
            config: TestConfig dengan ticker, date range, strategy, params.
            progress_callback: Optional callback untuk stream progress events.
                Dipanggil dengan dict: {"type": "step"|"done"|"error", ...}

        Returns:
            Dict dengan "summary" (TestSummary) dan "results" (list[TestResult]).
        """
        from trading_system.analysis.technical import TechnicalAnalysisEngine

        if config.strategy not in STRATEGIES:
            raise ValueError(f"Unknown strategy: {config.strategy}. Available: {list(STRATEGIES.keys())}")

        strategy_fn = STRATEGIES[config.strategy]
        params = config.params

        # Load full OHLCV untuk ticker (sekali, lalu slice per tanggal T)
        full_df = self.storage.load_ohlcv(config.ticker)
        if full_df.empty:
            if progress_callback:
                progress_callback({"type": "error", "message": f"No OHLCV data for {config.ticker}"})
            raise ValueError(f"No OHLCV data for {config.ticker}")

        # Parse date range
        start = pd.Timestamp(config.start_date)
        end = pd.Timestamp(config.end_date)

        # Filter trading days dalam range
        test_dates = full_df.index[(full_df.index >= start) & (full_df.index <= end)]
        # Step: ambil setiap N-th trading day
        test_dates = test_dates[::config.step]

        if len(test_dates) == 0:
            if progress_callback:
                progress_callback({"type": "error", "message": "No trading days in specified range"})
            raise ValueError("No trading days in specified range")

        if progress_callback:
            progress_callback({
                "type": "start",
                "ticker": config.ticker,
                "strategy": config.strategy,
                "total_steps": len(test_dates),
                "horizon": config.horizon,
                "date_range": f"{config.start_date} → {config.end_date}",
            })

        results: list[TestResult] = []
        equity = 100_000_000.0  # starting capital untuk simulated equity curve
        initial_equity = equity
        equity_curve = [{"date": test_dates[0].strftime("%Y-%m-%d"), "equity": equity}]
        position = 0  # 0 = flat, 1 = long, -1 = short
        position_price = 0.0

        for i, t in enumerate(test_dates):
            # PIT-safe: hanya pakai data up to T
            slice_df = full_df.loc[:t].copy()
            if len(slice_df) < config.min_history:
                if progress_callback and i % 10 == 0:
                    progress_callback({
                        "type": "skip",
                        "step": i + 1,
                        "total": len(test_dates),
                        "date": t.strftime("%Y-%m-%d"),
                        "reason": f"insufficient history ({len(slice_df)} < {config.min_history})",
                    })
                continue

            # Compute technical indicators pada slice
            try:
                eng = TechnicalAnalysisEngine()
                eng.ohlcv = slice_df
                indicators = eng.compute_indicators()
            except Exception as e:
                if progress_callback:
                    progress_callback({
                        "type": "error_step",
                        "step": i + 1,
                        "date": t.strftime("%Y-%m-%d"),
                        "error": str(e),
                    })
                continue

            # Generate prediction
            prediction, conviction = strategy_fn(indicators, params)

            # Snapshot indikator
            last_ind = indicators.iloc[-1]
            ind_snapshot = {
                "rsi": float(last_ind.get("rsi")) if not pd.isna(last_ind.get("rsi")) else None,
                "ma_50": float(last_ind.get("ma_50")) if not pd.isna(last_ind.get("ma_50")) else None,
                "adx": float(last_ind.get("adx")) if not pd.isna(last_ind.get("adx")) else None,
                "macd_hist": float(last_ind.get("macd", 0) - last_ind.get("macd_signal", 0))
                if not pd.isna(last_ind.get("macd")) and not pd.isna(last_ind.get("macd_signal"))
                else None,
            }

            # Actual return: T -> T+horizon
            future_idx = full_df.index.get_loc(t)
            future_pos = future_idx + config.horizon
            if future_pos >= len(full_df):
                # Tidak ada data future (akhir dataset)
                if progress_callback:
                    progress_callback({
                        "type": "skip",
                        "step": i + 1,
                        "total": len(test_dates),
                        "date": t.strftime("%Y-%m-%d"),
                        "reason": "no future data for evaluation",
                    })
                continue

            price_at_t = float(slice_df["close"].iloc[-1])
            price_at_t_plus = float(full_df["close"].iloc[future_pos])
            actual_return = ((price_at_t_plus - price_at_t) / price_at_t) * 100

            # Actual direction
            threshold = params.get("flat_threshold", 0.5)  # % return di bawah ini = FLAT
            if actual_return > threshold:
                actual_direction = "UP"
            elif actual_return < -threshold:
                actual_direction = "DOWN"
            else:
                actual_direction = "FLAT"

            # Correctness: BUY→UP, SELL→DOWN, HOLD→FLAT atau tidak salah arah
            if prediction == "BUY":
                correct = actual_direction in ("UP", "FLAT")
            elif prediction == "SELL":
                correct = actual_direction in ("DOWN", "FLAT")
            else:  # HOLD
                correct = actual_direction == "FLAT" or abs(actual_return) < 2.0

            result = TestResult(
                date=t.strftime("%Y-%m-%d"),
                prediction=prediction,
                conviction=conviction,
                actual_return=round(actual_return, 4),
                actual_direction=actual_direction,
                correct=correct,
                price_at_t=round(price_at_t, 2),
                price_at_t_plus=round(price_at_t_plus, 2),
                indicators=ind_snapshot,
            )
            results.append(result)

            # Simulated equity: ikuti prediksi
            if prediction == "BUY" and position == 0:
                position = 1
                position_price = price_at_t
            elif prediction == "SELL" and position == 1:
                position = 0
                pnl = (price_at_t - position_price) / position_price
                equity *= (1 + pnl)
                position_price = 0.0
            # Mark-to-market untuk equity curve
            if position == 1:
                mtm_equity = equity * (price_at_t_plus / price_at_t) if price_at_t > 0 else equity
            else:
                mtm_equity = equity
            equity_curve.append({"date": t.strftime("%Y-%m-%d"), "equity": round(mtm_equity, 2)})

            if progress_callback:
                status = "PASS" if correct else "FAIL"
                progress_callback({
                    "type": "step",
                    "step": i + 1,
                    "total": len(test_dates),
                    "date": t.strftime("%Y-%m-%d"),
                    "prediction": prediction,
                    "conviction": round(conviction, 1),
                    "actual_return": round(actual_return, 2),
                    "actual_direction": actual_direction,
                    "correct": correct,
                    "status": status,
                    "price": round(price_at_t, 2),
                })

        # Compute summary
        summary = self._compute_summary(results, config, equity_curve, initial_equity)

        if progress_callback:
            progress_callback({
                "type": "done",
                "summary": {
                    "ticker": summary.ticker,
                    "strategy": summary.strategy,
                    "total_predictions": summary.total_predictions,
                    "correct_predictions": summary.correct_predictions,
                    "accuracy": round(summary.accuracy, 2),
                    "buy_count": summary.buy_count,
                    "sell_count": summary.sell_count,
                    "hold_count": summary.hold_count,
                    "buy_accuracy": round(summary.buy_accuracy, 2),
                    "sell_accuracy": round(summary.sell_accuracy, 2),
                    "hold_accuracy": round(summary.hold_accuracy, 2),
                    "mean_actual_return": round(summary.mean_actual_return, 4),
                    "final_equity": equity_curve[-1]["equity"] if equity_curve else initial_equity,
                },
            })

        return {
            "config": {
                "ticker": config.ticker,
                "start_date": config.start_date,
                "end_date": config.end_date,
                "horizon": config.horizon,
                "step": config.step,
                "strategy": config.strategy,
                "params": config.params,
            },
            "summary": {
                "ticker": summary.ticker,
                "strategy": summary.strategy,
                "total_predictions": summary.total_predictions,
                "correct_predictions": summary.correct_predictions,
                "accuracy": round(summary.accuracy, 4),
                "buy_count": summary.buy_count,
                "sell_count": summary.sell_count,
                "hold_count": summary.hold_count,
                "buy_accuracy": round(summary.buy_accuracy, 4),
                "sell_accuracy": round(summary.sell_accuracy, 4),
                "hold_accuracy": round(summary.hold_accuracy, 4),
                "confusion_matrix": summary.confusion_matrix,
                "mean_actual_return": round(summary.mean_actual_return, 4),
                "sharpe_of_predictions": round(summary.sharpe_of_predictions, 4),
                "final_equity": equity_curve[-1]["equity"] if equity_curve else initial_equity,
                "initial_equity": initial_equity,
            },
            "results": [
                {
                    "date": r.date,
                    "prediction": r.prediction,
                    "conviction": r.conviction,
                    "actual_return": r.actual_return,
                    "actual_direction": r.actual_direction,
                    "correct": r.correct,
                    "price_at_t": r.price_at_t,
                    "price_at_t_plus": r.price_at_t_plus,
                    "indicators": r.indicators,
                }
                for r in results
            ],
            "equity_curve": equity_curve,
        }

    def _compute_summary(
        self, results: list[TestResult], config: TestConfig,
        equity_curve: list, initial_equity: float,
    ) -> TestSummary:
        total = len(results)
        correct = sum(1 for r in results if r.correct)

        buy_results = [r for r in results if r.prediction == "BUY"]
        sell_results = [r for r in results if r.prediction == "SELL"]
        hold_results = [r for r in results if r.prediction == "HOLD"]

        buy_correct = sum(1 for r in buy_results if r.correct)
        sell_correct = sum(1 for r in sell_results if r.correct)
        hold_correct = sum(1 for r in hold_results if r.correct)

        # Confusion matrix: {predicted: {actual: count}}
        confusion = {"BUY": {"UP": 0, "DOWN": 0, "FLAT": 0},
                     "SELL": {"UP": 0, "DOWN": 0, "FLAT": 0},
                     "HOLD": {"UP": 0, "DOWN": 0, "FLAT": 0}}
        for r in results:
            confusion[r.prediction][r.actual_direction] += 1

        # Mean actual return
        mean_ret = float(np.mean([r.actual_return for r in results])) if results else 0.0

        # Sharpe of predictions: treat correct=+1, incorrect=-1 as returns
        pred_returns = [1.0 if r.correct else -1.0 for r in results]
        if len(pred_returns) > 1:
            sharpe = float(np.mean(pred_returns) / (np.std(pred_returns, ddof=1) + 1e-9) * np.sqrt(252))
        else:
            sharpe = 0.0

        return TestSummary(
            ticker=config.ticker,
            strategy=config.strategy,
            total_predictions=total,
            correct_predictions=correct,
            accuracy=(correct / total * 100) if total > 0 else 0.0,
            buy_count=len(buy_results),
            sell_count=len(sell_results),
            hold_count=len(hold_results),
            buy_accuracy=(buy_correct / len(buy_results) * 100) if buy_results else 0.0,
            sell_accuracy=(sell_correct / len(sell_results) * 100) if sell_results else 0.0,
            hold_accuracy=(hold_correct / len(hold_results) * 100) if hold_results else 0.0,
            confusion_matrix=confusion,
            mean_actual_return=mean_ret,
            sharpe_of_predictions=sharpe,
            equity_curve=equity_curve,
        )
