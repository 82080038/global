"""Strategi benchmark untuk Phase 1."""

from __future__ import annotations

import pandas as pd

from trading_system.config import EXIT_CONVICTION_THRESHOLD


class BuyAndHold:
    """Beli di hari pertama, hold sampai akhir."""

    name = "buy_and_hold"
    warmup_periods = 0  # No warmup needed

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["signal"] = 0
        df.iloc[0, df.columns.get_loc("signal")] = 1
        df.iloc[-1, df.columns.get_loc("signal")] = -1
        return df


class MovingAverageCrossover:
    """MA sederhana: fast > slow -> BUY, fast < slow -> SELL."""

    def __init__(self, fast: int = 20, slow: int = 50):
        self.fast = fast
        self.slow = slow
        self.name = f"ma_crossover_{fast}_{slow}"
        self.warmup_periods = slow  # Need at least `slow` bars before signals are valid

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df[f"ma_{self.fast}"] = df["close"].rolling(self.fast).mean()
        df[f"ma_{self.slow}"] = df["close"].rolling(self.slow).mean()
        df["signal"] = 0

        # Warmup: no signals until both MAs are valid (point-in-time safety)
        warmup = self.warmup_periods
        if len(df) <= warmup:
            return df

        fast_col = f"ma_{self.fast}"
        slow_col = f"ma_{self.slow}"

        # Only generate signals after warmup period to avoid look-ahead bias
        buy = (df[fast_col] > df[slow_col]) & (df.index >= df.index[warmup])
        sell = (df[fast_col] < df[slow_col]) & (df.index >= df.index[warmup])

        # Hanya sinyal pada crossing (point-in-time: uses only current and previous bar)
        df.loc[buy & (df[fast_col].shift(1) <= df[slow_col].shift(1)), "signal"] = 1
        df.loc[sell & (df[fast_col].shift(1) >= df[slow_col].shift(1)), "signal"] = -1
        return df


class ConvictionStrategy:
    """Backtest strategi conviction multi-factor (§3.2 SARAN_PENGEMBANGAN.md).

    Mereplay skor historis dari tabel ``scores`` (point-in-time) dan
    menghasilkan sinyal sesuai logika yang sama dengan ``DecisionEngine.decide_action``:

    - conviction >= 70 → BUY (signal = 1)
    - conviction < EXIT_CONVICTION_THRESHOLD dan ada posisi → SELL (signal = -1)
    - sisanya → HOLD (signal = 0)

    Jika tidak ada skor historis untuk ticker ini, fallback ke BUY when
    conviction >= 70 (menggunakan skor yang di-pass via ``scores_df``).
    """

    name = "conviction"
    warmup_periods = 0

    def __init__(self, storage=None, ticker: str | None = None,
                 buy_threshold: float = 70, exit_threshold: float = EXIT_CONVICTION_THRESHOLD,
                 scores_df: pd.DataFrame | None = None):
        self.storage = storage
        self.ticker = ticker
        self.buy_threshold = buy_threshold
        self.exit_threshold = exit_threshold
        self._scores_df = scores_df

    def _load_scores(self) -> pd.DataFrame:
        if self._scores_df is not None:
            return self._scores_df
        if self.storage is None:
            return pd.DataFrame()
        df = self.storage.load_scores(ticker=self.ticker)
        if df.empty:
            return df
        # Aggregate per as_of: weighted average of engine scores
        df["as_of"] = pd.to_datetime(df["as_of"])
        df = df.sort_values("as_of")
        # Group by timestamp, average the scores
        agg = df.groupby("as_of")["score"].mean().reset_index()
        agg.rename(columns={"score": "conviction"}, inplace=True)
        return agg

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["signal"] = 0

        scores = self._load_scores()
        if scores.empty:
            return df

        # Merge scores onto OHLCV by nearest prior timestamp (point-in-time)
        scores = scores.sort_values("as_of")
        df = pd.merge_asof(
            df.reset_index(),
            scores,
            left_on="timestamp",
            right_on="as_of",
            direction="backward",
        )
        if "conviction" not in df.columns:
            df["conviction"] = float("nan")
        df.set_index("timestamp", inplace=True)

        # Track position state to generate SELL only when holding
        in_position = False
        signals = []
        for _, row in df.iterrows():
            conv = row.get("conviction")
            if pd.isna(conv):
                signals.append(0)
                continue
            conv = float(conv)
            if not in_position and conv >= self.buy_threshold:
                signals.append(1)
                in_position = True
            elif in_position and conv < self.exit_threshold:
                signals.append(-1)
                in_position = False
            else:
                signals.append(0)

        df["signal"] = signals
        # Drop helper columns
        for col in ("conviction", "as_of"):
            if col in df.columns:
                df.drop(columns=[col], inplace=True)
        return df
