"""Playwright headed-browser visualization for replay simulation results.

Membuka dashboard aplikasi trading system dan menampilkan hasil replay:
1. Dashboard — analisis ticker, recommendation, scores
2. Portfolio — posisi dan PnL
3. Audit — history trade replay
4. Backtest — perbandingan dengan backtest buy_and_hold

Penggunaan:
    ./venv/bin/python tests/e2e/visualize_replay.py [--ticker BBCA.JK]

Prasyarat:
    - API server di http://localhost:8000
    - Frontend di http://localhost:3000
    - replay_simulation.py sudah dijalankan
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright

BASE_URL = "http://localhost:3000"
API_URL = "http://localhost:8000"
SCREEN_DIR = Path(__file__).parent / "screenshots"
SCREEN_DIR.mkdir(parents=True, exist_ok=True)


def _screenshot(page: Page, name: str):
    path = SCREEN_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    print(f"  Screenshot: {path}")


def visualize_dashboard(page: Page, ticker: str):
    """Buka dashboard dan analisis ticker."""
    print(f"\n[1/5] Dashboard — Analyze {ticker}")
    page.goto(f"{BASE_URL}/dashboard")
    page.wait_for_selector("h1", timeout=15_000)

    # Isi ticker dan analyze
    ticker_input = page.locator("input[placeholder='Ticker (e.g. BBCA.JK)']")
    if ticker_input.count() > 0:
        ticker_input.fill(ticker)
        page.locator("button:has-text('Analyze')").click()
        # Wait for recommendation
        try:
            page.locator("text=/BUY|HOLD|WATCHLIST|AVOID|SELL/").first.wait_for(timeout=30_000)
            time.sleep(2)
        except PWTimeout:
            print("  WARNING: Timeout waiting for recommendation")
    _screenshot(page, "01_dashboard_analysis")


def visualize_portfolio(page: Page):
    """Buka portfolio page untuk lihat posisi dan PnL."""
    print("\n[2/5] Portfolio — Positions & PnL")
    page.goto(f"{BASE_URL}/portfolio")
    page.wait_for_selector("h1", timeout=15_000)
    time.sleep(2)
    _screenshot(page, "02_portfolio_positions")


def visualize_audit(page: Page):
    """Buka audit page untuk lihat trade history."""
    print("\n[3/5] Audit — Trade History")
    page.goto(f"{BASE_URL}/audit")
    page.wait_for_selector("h1", timeout=15_000)
    time.sleep(2)
    _screenshot(page, "03_audit_trades")


def visualize_engines(page: Page):
    """Buka engines page untuk lihat status engine."""
    print("\n[4/5] Engines — System Status")
    page.goto(f"{BASE_URL}/engines")
    page.wait_for_selector("h1", timeout=15_000)
    time.sleep(2)
    _screenshot(page, "04_engines_status")


def visualize_backtest(page: Page, ticker: str, capital: float, months: int):
    """Buka backtest page dan jalankan backtest perbandingan."""
    print(f"\n[5/5] Backtest — Buy & Hold comparison ({ticker})")
    page.goto(f"{BASE_URL}/backtest")
    page.wait_for_selector("h1:has-text('Backtest')", timeout=15_000)

    # Isi form
    page.locator("input[placeholder='e.g. BBCA.JK']").fill(ticker)
    page.locator("select").select_option("buy_and_hold")
    page.locator("input[placeholder='Capital (IDR)']").fill(str(int(capital)))

    # Isi tanggal (12 bulan terakhir)
    from datetime import datetime, timedelta
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=months * 30)).strftime("%Y-%m-%d")
    page.locator("input[type='date']").nth(0).fill(start_date)
    page.locator("input[type='date']").nth(1).fill(end_date)

    # Run backtest
    page.locator("button:has-text('Run Backtest')").click()
    try:
        page.locator("text=Total Return").wait_for(timeout=60_000)
        time.sleep(1)
    except PWTimeout:
        print("  WARNING: Timeout waiting for backtest result")
    _screenshot(page, "05_backtest_comparison")


def show_summary(page: Page, results: dict):
    """Tampilkan summary hasil replay di browser."""
    print("\n[Summary] Replay Results")

    # Buka dashboard dan inject summary HTML
    page.goto(f"{BASE_URL}/dashboard")
    time.sleep(1)

    # Inject summary overlay
    summary_html = f"""
    <div style="position:fixed;top:10px;right:10px;z-index:9999;
                background:#1a1a2e;color:#e0e0e0;padding:20px;
                border:2px solid #0f3460;border-radius:8px;
                font-family:monospace;font-size:14px;max-width:400px;
                box-shadow:0 4px 20px rgba(0,0,0,0.5);">
        <h2 style="color:#e94560;margin:0 0 10px 0;">Replay Simulation Summary</h2>
        <hr style="border:0;border-top:1px solid #0f3460;margin:10px 0;">
        <p><b>Ticker:</b> {results.get('ticker', 'N/A')}</p>
        <p><b>Initial Capital:</b> Rp {results.get('initial_capital', 0):,.0f}</p>
        <p><b>Final Equity:</b> Rp {results.get('final_equity', 0):,.0f}</p>
        <p><b>Total Return:</b> <span style="color:{'#4ecca3' if results.get('total_return_pct', 0) >= 0 else '#e94560'};">
            {results.get('total_return_pct', 0):+.2f}%</span></p>
        <p><b>Realized PnL:</b> Rp {results.get('total_realized_pnl', 0):,.0f}</p>
        <p><b>Total Fees:</b> Rp {results.get('total_fees', 0):,.0f}</p>
        <p><b>Sharpe Ratio:</b> {results.get('sharpe_ratio', 0):.4f}</p>
        <p><b>Max Drawdown:</b> {results.get('max_drawdown_pct', 0):.2f}%</p>
        <hr style="border:0;border-top:1px solid #0f3460;margin:10px 0;">
        <p><b>Trading Days:</b> {results.get('n_trading_days', 0)}</p>
        <p><b>Trades:</b> {results.get('n_buys', 0)} buys, {results.get('n_sells', 0)} sells</p>
        <p style="padding-left:20px;">
            Stop Loss: {results.get('n_stop_loss', 0)} |
            Take Profit: {results.get('n_take_profit', 0)} |
            Trailing: {results.get('n_trailing_stop', 0)} |
            Signal: {results.get('n_signal_sell', 0)}
        </p>
        <hr style="border:0;border-top:1px solid #0f3460;margin:10px 0;">
        <p style="font-size:11px;color:#888;">Full pipeline: TechnicalAnalysis → DecisionEngine → RiskEngine → CostModel → Portfolio</p>
    </div>
    """
    page.evaluate(f"document.body.insertAdjacentHTML('beforeend', {json.dumps(summary_html)})")
    time.sleep(3)
    _screenshot(page, "06_replay_summary")


def main():
    parser = argparse.ArgumentParser(description="Visualize replay simulation results")
    parser.add_argument("--ticker", default="BBCA.JK", help="Ticker symbol")
    parser.add_argument("--capital", type=float, default=10_000_000, help="Initial capital")
    parser.add_argument("--months", type=int, default=12, help="Replay period in months")
    args = parser.parse_args()

    # Load replay results
    results_file = Path(__file__).resolve().parents[2] / "scripts" / "replay_results.json"
    if not results_file.exists():
        print(f"ERROR: {results_file} not found. Run replay_simulation.py first.")
        return

    with open(results_file) as f:
        results = json.load(f)

    print("=" * 70)
    print("  PLAYWRIGHT VISUALIZATION — REPLAY SIMULATION RESULTS")
    print("=" * 70)
    print(f"  Ticker: {results.get('ticker', args.ticker)}")
    print(f"  Final Equity: Rp {results.get('final_equity', 0):,.0f}")
    print(f"  Total Return: {results.get('total_return_pct', 0):+.2f}%")
    print(f"  Trades: {results.get('n_buys', 0)} buys, {results.get('n_sells', 0)} sells")
    print("=" * 70)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--no-sandbox"])
        context = browser.new_context(
            viewport={"width": 1400, "height": 900},
            record_video_dir=str(SCREEN_DIR / "videos"),
            record_video_size={"width": 1400, "height": 900},
        )
        page = context.new_page()

        # 1. Dashboard — analyze ticker
        visualize_dashboard(page, args.ticker)

        # 2. Portfolio — positions & PnL
        visualize_portfolio(page)

        # 3. Audit — trade history
        visualize_audit(page)

        # 4. Engines — system status
        visualize_engines(page)

        # 5. Backtest — buy & hold comparison
        visualize_backtest(page, args.ticker, args.capital, args.months)

        # 6. Summary overlay
        show_summary(page, results)

        print("\n" + "=" * 70)
        print("  VISUALIZATION COMPLETE")
        print(f"  Screenshots: {SCREEN_DIR}/")
        print("=" * 70)
        print("\n  Browser akan tertutup dalam 15 detik...")
        time.sleep(15)

        context.close()
        browser.close()


if __name__ == "__main__":
    main()
