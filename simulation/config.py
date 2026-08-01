"""Konfigurasi simulasi — semua parameter di satu tempat."""

from __future__ import annotations

import os
from pathlib import Path

# ── Path ──────────────────────────────────────────────────────────────
SIMULATION_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SIMULATION_DIR.parent
REPORT_DIR = SIMULATION_DIR / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# ── Tickers ───────────────────────────────────────────────────────────
DEFAULT_TICKERS = os.getenv("SIM_TICKERS", "BBCA.JK,TLKM.JK,ASII.JK,UNVR.JK,BMRI.JK").split(",")
PRIMARY_TICKER = DEFAULT_TICKERS[0]

# ── Modal & Risk ──────────────────────────────────────────────────────
SIM_CAPITAL = float(os.getenv("SIM_CAPITAL", "100000000"))  # Rp 100 juta
SIM_RISK_PER_TRADE = float(os.getenv("SIM_RISK_PER_TRADE", "0.01"))

# ── Backtest ──────────────────────────────────────────────────────────
SIM_BACKTEST_STRATEGIES = ["buy_and_hold", "ma_crossover", "conviction"]
SIM_MC_RUNS = int(os.getenv("SIM_MC_RUNS", "500"))
SIM_WF_SPLITS = int(os.getenv("SIM_WF_SPLITS", "5"))

# ── API ───────────────────────────────────────────────────────────────
API_BASE = os.getenv("API_BASE", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", "dev_b11174160ce59a0e4e9901baef84c1d2")

# ── Hasil ─────────────────────────────────────────────────────────────
results: list[dict] = []


def record(module: str, test: str, status: str, detail: str = "", data: dict | None = None):
    """Catat hasil test ke list global."""
    entry = {
        "module": module,
        "test": test,
        "status": status,
        "detail": detail,
    }
    if data:
        entry["data"] = data
    results.append(entry)
    icon = {"pass": "PASS", "fail": "FAIL", "warn": "WARN", "skip": "SKIP"}.get(status, status)
    print(f"  [{icon}] {module}/{test}: {detail}")
    return entry
