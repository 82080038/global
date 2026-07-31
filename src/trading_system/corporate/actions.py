"""Corporate Action Engine (Fase 3).

Mengambil split, dividend, dan actions dari yfinance, menyimpan,
dan menghitung adjustment factor untuk harga adjusted.
"""

from __future__ import annotations

import pandas as pd
import yfinance as yf

from trading_system.data.storage import DataStorage


class CorporateActionEngine:
    name = "corporate_action"

    def __init__(self, storage: DataStorage | None = None):
        self.storage = storage or DataStorage()

    def fetch(self, ticker: str):
        t = yf.Ticker(ticker)
        try:
            splits = t.splits.to_frame(name="value") if t.splits is not None and not t.splits.empty else pd.DataFrame()
            divs = t.dividends.to_frame(name="value") if t.dividends is not None and not t.dividends.empty else pd.DataFrame()
        except Exception as e:
            return {"status": "error", "message": str(e)}

        records = []
        for idx, row in splits.iterrows():
            records.append({
                "ticker": ticker,
                "action_type": "split",
                "announce_date": None,
                "ex_date": pd.to_datetime(idx).strftime("%Y-%m-%d"),
                "record_date": None,
                "payment_date": None,
                "value": float(row["value"]),
                "unit": "ratio",
                "source": "yfinance",
            })
        for idx, row in divs.iterrows():
            records.append({
                "ticker": ticker,
                "action_type": "dividend",
                "announce_date": None,
                "ex_date": pd.to_datetime(idx).strftime("%Y-%m-%d"),
                "record_date": None,
                "payment_date": None,
                "value": float(row["value"]),
                "unit": "IDR_per_share" if ticker.endswith(".JK") else "currency_per_share",
                "source": "yfinance",
            })

        for r in records:
            self.storage.save_corporate_action(r)

        return {
            "status": "ok",
            "ticker": ticker,
            "actions": records,
            "count": len(records),
        }

    def compute_adjustment_factor(self, ticker: str) -> pd.DataFrame:
        """Hitung adjustment factor kumulatif (backward) untuk harga close.

        Backward adjustment: pre-event prices are scaled to be comparable
        to post-event prices. For splits, pre-split prices are divided by
        the split ratio. For dividends, pre-dividend prices are multiplied
        by (close_before_ex - dividend) / close_before_ex.
        """
        df = self.storage.load_ohlcv(ticker)
        actions = self.storage.load_corporate_actions(ticker)
        if df.empty:
            return pd.DataFrame()

        df = df.copy()
        df["adj_factor"] = 1.0
        df["adj_close"] = df["close"]

        if actions.empty:
            return df

        actions = actions.sort_values("ex_date", ascending=False)
        for _, act in actions.iterrows():
            ex = pd.to_datetime(act.get("ex_date"))
            atype = act.get("action_type")
            value = float(act.get("value", 0))
            if ex > df.index[-1]:
                continue
            if atype == "split" and value > 0:
                # Split ratio from yfinance is new:old (e.g., 2:1 = 2.0).
                # Backward-adjust: pre-split prices *= 1/ratio
                mask = df.index < ex
                df.loc[mask, "adj_factor"] *= 1.0 / value
            elif atype == "dividend" and value > 0:
                # Dividend adjustment: pre-dividend prices *= (close_before_ex - dividend) / close_before_ex
                pre_mask = df.index < ex
                pre_prices = df.loc[pre_mask, "close"]
                if not pre_prices.empty:
                    last_close_before_ex = float(pre_prices.iloc[-1])
                    if last_close_before_ex > value:
                        ratio = (last_close_before_ex - value) / last_close_before_ex
                        df.loc[pre_mask, "adj_factor"] *= ratio

        df["adj_close"] = df["close"] * df["adj_factor"]
        return df
