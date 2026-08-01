"""Playwright headed-browser simulation for trading system.

Menjalankan simulasi lengkap (Backtest, Monte Carlo, Walk-Forward) untuk
satu ticker dengan modal Rp 10.000.000 selama 1 tahun terakhir.

Penggunaan:
    ./venv/bin/python tests/e2e/run_simulation.py [--ticker BBCA.JK]
                                                  [--capital 10000000]
                                                  [--months 12]

Prasyarat:
    - API server berjalan di http://localhost:8000
    - Frontend berjalan di http://localhost:3000
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PWTimeout, expect, sync_playwright

BASE_URL = "http://localhost:3000"
API_URL = "http://localhost:8000"
SCREEN_DIR = Path(__file__).parent / "screenshots"
SCREEN_DIR.mkdir(parents=True, exist_ok=True)


def _screenshot(page: Page, name: str):
    path = SCREEN_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    print(f"  Screenshot: {path}")


def _wait_for_result(page: Page, timeout_ms: int = 60_000):
    """Tunggu hasil backtest muncul (StatCard dengan label 'Total Return')."""
    page.locator("text=Total Return").wait_for(timeout=timeout_ms)


def run_backtest_ui(page: Page, ticker: str, capital: int, start: str, end: str, strategy: str = "buy_and_hold"):
    """Jalankan backtest melalui UI."""
    print(f"\n[Backtest] {ticker} | {strategy} | Rp {capital:,} | {start} → {end}")

    page.goto(f"{BASE_URL}/backtest")
    page.wait_for_selector("h1:has-text('Backtest')", timeout=15_000)

    # Isi ticker
    ticker_input = page.locator("input[placeholder='e.g. BBCA.JK']")
    ticker_input.fill(ticker)

    # Pilih strategi
    page.locator("select").select_option(strategy)

    # Isi modal
    capital_input = page.locator("input[placeholder='Capital (IDR)']")
    capital_input.fill(str(capital))

    # Isi tanggal
    page.locator("input[type='date']").nth(0).fill(start)
    page.locator("input[type='date']").nth(1).fill(end)

    _screenshot(page, f"01_backtest_form_{ticker}_{strategy}")

    # Klik Run Backtest
    page.locator("button:has-text('Run Backtest')").click()

    # Tunggu hasil
    try:
        _wait_for_result(page, timeout_ms=90_000)
    except PWTimeout:
        print("  WARNING: Timeout menunggu hasil backtest")
        _screenshot(page, f"01b_backtest_timeout_{ticker}_{strategy}")
        return None

    time.sleep(1)
    _screenshot(page, f"02_backtest_result_{ticker}_{strategy}")

    # Baca metrik dari StatCards
    stats = {}
    stat_cards = page.locator("div:has(> div.text-xs.text-zinc-500)")
    for i in range(stat_cards.count()):
        card = stat_cards.nth(i)
        label = card.locator("div.text-xs.text-zinc-500").text_content().strip()
        value = card.locator("div.text-sm.font-bold").text_content().strip()
        stats[label] = value

    print(f"  Result: {stats}")
    return stats


def run_monte_carlo_api(page: Page, ticker: str, capital: int, start: str, end: str, n_sim: int = 1000):
    """Jalankan Monte Carlo via API (tidak ada UI page untuk ini)."""
    print(f"\n[Monte Carlo] {ticker} | {n_sim} runs | Rp {capital:,} | {start} → {end}")

    payload = json.dumps({
        "ticker": ticker,
        "n_simulations": n_sim,
        "capital": capital,
        "start": start,
        "end": end,
    })

    result = page.evaluate(
        """async (payload) => {
            const res = await fetch('""" + API_URL + """/api/backtest/monte-carlo', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: payload,
            });
            return await res.json();
        }""",
        payload,
    )

    print(f"  Result: {json.dumps(result, indent=2, default=str)[:500]}")
    return result


def run_walk_forward_api(page: Page, ticker: str, start: str, end: str, strategy: str = "ma_crossover"):
    """Jalankan Walk-Forward via API."""
    print(f"\n[Walk-Forward] {ticker} | {strategy} | {start} → {end}")

    payload = json.dumps({
        "ticker": ticker,
        "strategy": strategy,
        "n_splits": 5,
        "start": start,
        "end": end,
    })

    result = page.evaluate(
        """async (payload) => {
            const res = await fetch('""" + API_URL + """/api/backtest/walk-forward', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: payload,
            });
            return await res.json();
        }""",
        payload,
    )

    print(f"  Result: {json.dumps(result, indent=2, default=str)[:500]}")
    return result


def main():
    parser = argparse.ArgumentParser(description="Playwright headed simulation")
    parser.add_argument("--ticker", default="BBCA.JK", help="Ticker simbol (default: BBCA.JK)")
    parser.add_argument("--capital", type=int, default=10_000_000, help="Modal awal IDR (default: 10 juta)")
    parser.add_argument("--months", type=int, default=12, help="Rentang waktu dalam bulan (default: 12)")
    parser.add_argument("--strategy", default="buy_and_hold", help="Strategi: buy_and_hold, ma_crossover, conviction")
    args = parser.parse_args()

    # Hitung rentang tanggal
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=args.months * 30)).strftime("%Y-%m-%d")

    print("=" * 60)
    print("  TRADING SYSTEM - PLAYWRIGHT HEADED SIMULATION")
    print("=" * 60)
    print(f"  Ticker   : {args.ticker}")
    print(f"  Modal    : Rp {args.capital:,}")
    print(f"  Periode  : {start_date} → {end_date} ({args.months} bulan)")
    print(f"  Strategi : {args.strategy}")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--no-sandbox"])
        context = browser.new_context(
            viewport={"width": 1400, "height": 900},
            record_video_dir=str(SCREEN_DIR / "videos"),
            record_video_size={"width": 1400, "height": 900},
        )
        page = context.new_page()

        # 1. Backtest via UI
        stats = run_backtest_ui(page, args.ticker, args.capital, start_date, end_date, args.strategy)

        # 2. Monte Carlo via API (dari browser context)
        mc_result = run_monte_carlo_api(page, args.ticker, args.capital, start_date, end_date)

        # 3. Walk-Forward via API
        wf_result = run_walk_forward_api(page, args.ticker, start_date, end_date, strategy="ma_crossover")

        # Screenshot final
        _screenshot(page, "99_final_summary")

        print("\n" + "=" * 60)
        print("  SIMULASI SELESAI")
        print("=" * 60)
        if stats:
            print("  Backtest:")
            for k, v in stats.items():
                print(f"    {k}: {v}")
        if mc_result and "status" not in mc_result:
            print(f"  Monte Carlo: {len(mc_result.get('simulations', []))} runs")
        if wf_result and "status" not in wf_result:
            print(f"  Walk-Forward: {len(wf_result.get('splits', []))} splits")
        print(f"\n  Screenshots: {SCREEN_DIR}/")
        print("=" * 60)

        # Tahan browser terbuka sebentar agar user bisa lihat
        print("\n  Browser akan tertutup dalam 10 detik...")
        time.sleep(10)

        context.close()
        browser.close()


if __name__ == "__main__":
    main()
