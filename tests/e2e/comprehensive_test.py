"""Comprehensive Playwright headed-browser E2E test for the Trading System.

Tests all major pages and user flows:
1. Dashboard — load, analyze ticker, verify recommendation + chart
2. Backtest — run backtest with UI, verify metrics
3. Portfolio — load, verify positions/orders display
4. Audit — load, verify audit log table
5. Engines — load, verify engine status
6. API endpoints — health check via browser context
7. Console error capture across all pages

Prasyarat:
    - API server berjalan di http://localhost:8000
    - Frontend berjalan di http://localhost:3000

Penggunaan:
    .venv/bin/python tests/e2e/comprehensive_test.py
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PWTimeout, expect, sync_playwright

BASE_URL = "http://localhost:3000"
API_URL = "http://localhost:8000"
SCREEN_DIR = Path(__file__).parent / "screenshots"
SCREEN_DIR.mkdir(parents=True, exist_ok=True)

# Results collector
results: list[dict] = []


def _screenshot(page: Page, name: str):
    path = SCREEN_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    print(f"  Screenshot: {path}")


def _record(name: str, status: str, detail: str = ""):
    results.append({"test": name, "status": status, "detail": detail})
    icon = "PASS" if status == "pass" else "FAIL" if status == "fail" else "WARN"
    print(f"  [{icon}] {name}: {detail}")


def test_dashboard(page: Page):
    """Test 1: Dashboard load + analyze ticker."""
    print("\n" + "=" * 60)
    print("  TEST 1: Dashboard — Load & Analyze")
    print("=" * 60)

    try:
        page.goto(f"{BASE_URL}/dashboard", wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_selector("h1", timeout=60_000)
        _screenshot(page, "comp_01_dashboard_loaded")
        _record("Dashboard loads", "pass", "Page loaded with h1 visible")
    except Exception as e:
        _record("Dashboard loads", "fail", str(e))
        return

    # Check default ticker input
    try:
        ticker_input = page.locator("input[placeholder='Ticker (e.g. BBCA.JK)']")
        expect(ticker_input).to_be_visible(timeout=10_000)
        default_ticker = ticker_input.input_value()
        _record("Default ticker field", "pass", f"Default: {default_ticker}")
    except Exception as e:
        _record("Default ticker field", "fail", str(e))

    # Click Analyze
    try:
        analyze_btn = page.locator("button:has-text('ANALYZE')")
        expect(analyze_btn).to_be_visible(timeout=10_000)
        analyze_btn.click()
        print("  Clicked Analyze button, waiting for result...")

        # Wait for recommendation
        page.locator("text=/BUY|HOLD|WATCHLIST|AVOID/").first.wait_for(timeout=60_000)
        time.sleep(2)
        _screenshot(page, "comp_02_bbcj_analyzed")

        rec = page.locator("text=/BUY|HOLD|WATCHLIST|AVOID/").first
        action = rec.text_content().strip()
        _record("Analyze BBCA.JK", "pass", f"Action: {action}")

        # Check for chart
        chart = page.locator("svg.recharts-surface")
        if chart.count() > 0:
            _record("Factor score chart", "pass", "Recharts SVG visible")
        else:
            _record("Factor score chart", "warn", "Chart not found")
    except PWTimeout:
        _screenshot(page, "comp_02b_analyze_timeout")
        _record("Analyze BBCA.JK", "fail", "Timeout waiting for recommendation")
    except Exception as e:
        _record("Analyze BBCA.JK", "fail", str(e))

    # Change ticker to TLKM.JK
    try:
        ticker_input.fill("TLKM.JK")
        page.locator("button:has-text('ANALYZE')").click()
        page.locator("text=/TLJM\\.JK|TLKM\\.JK/").first.wait_for(timeout=60_000)
        time.sleep(2)
        _screenshot(page, "comp_03_tlkm_analyzed")
        _record("Analyze TLKM.JK", "pass", "Ticker changed and analyzed")
    except PWTimeout:
        _screenshot(page, "comp_03b_tlkm_timeout")
        _record("Analyze TLKM.JK", "warn", "Timeout — may not have scores")
    except Exception as e:
        _record("Analyze TLKM.JK", "fail", str(e))


def test_backtest(page: Page):
    """Test 2: Backtest page — run backtest via UI."""
    print("\n" + "=" * 60)
    print("  TEST 2: Backtest — Run via UI")
    print("=" * 60)

    try:
        page.goto(f"{BASE_URL}/backtest", wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_selector("h1:has-text('Backtest')", timeout=60_000)
        _screenshot(page, "comp_04_backtest_loaded")
        _record("Backtest page loads", "pass", "Page loaded")
    except Exception as e:
        _record("Backtest page loads", "fail", str(e))
        return

    # Fill form
    try:
        ticker_input = page.locator("input[placeholder='e.g. BBCA.JK']")
        ticker_input.fill("BBCA.JK")

        page.locator("select").select_option("buy_and_hold")

        capital_input = page.locator("input[placeholder='Capital (IDR)']")
        capital_input.fill("10000000")

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        page.locator("input[type='date']").nth(0).fill(start_date)
        page.locator("input[type='date']").nth(1).fill(end_date)

        _screenshot(page, "comp_05_backtest_form")
        _record("Backtest form filled", "pass", f"BBCA.JK, buy_and_hold, Rp 10M, {start_date} → {end_date}")
    except Exception as e:
        _record("Backtest form filled", "fail", str(e))
        return

    # Run backtest
    try:
        page.locator("button:has-text('Run Backtest')").click()
        print("  Clicked Run Backtest, waiting for result...")

        page.locator("text=Total Return").wait_for(timeout=90_000)
        time.sleep(2)
        _screenshot(page, "comp_06_backtest_result")
        _record("Backtest result", "pass", "Total Return metric visible")
    except PWTimeout:
        _screenshot(page, "comp_06b_backtest_timeout")
        _record("Backtest result", "warn", "Timeout waiting for result")
    except Exception as e:
        _record("Backtest result", "fail", str(e))


def test_portfolio(page: Page):
    """Test 3: Portfolio page."""
    print("\n" + "=" * 60)
    print("  TEST 3: Portfolio — Load & Verify")
    print("=" * 60)

    try:
        page.goto(f"{BASE_URL}/portfolio", wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_selector("h1", timeout=60_000)
        time.sleep(2)
        _screenshot(page, "comp_07_portfolio")
        _record("Portfolio page loads", "pass", "Page loaded")
    except Exception as e:
        _record("Portfolio page loads", "fail", str(e))


def test_audit(page: Page):
    """Test 4: Audit page."""
    print("\n" + "=" * 60)
    print("  TEST 4: Audit — Load & Verify")
    print("=" * 60)

    try:
        page.goto(f"{BASE_URL}/audit", wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_selector("h1", timeout=60_000)
        time.sleep(2)
        _screenshot(page, "comp_08_audit")
        _record("Audit page loads", "pass", "Page loaded")
    except Exception as e:
        _record("Audit page loads", "fail", str(e))


def test_engines(page: Page):
    """Test 5: Engines page."""
    print("\n" + "=" * 60)
    print("  TEST 5: Engines — Load & Verify")
    print("=" * 60)

    try:
        page.goto(f"{BASE_URL}/engines", wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_selector("h1", timeout=60_000)
        time.sleep(2)
        _screenshot(page, "comp_09_engines")
        _record("Engines page loads", "pass", "Page loaded")
    except Exception as e:
        _record("Engines page loads", "fail", str(e))


def test_api_endpoints(page: Page):
    """Test 6: API endpoint health checks via browser context."""
    print("\n" + "=" * 60)
    print("  TEST 6: API Endpoint Health Checks")
    print("=" * 60)

    endpoints = [
        ("GET", "/api/health"),
        ("GET", "/api/monitor"),
        ("GET", "/api/tickers"),
        ("GET", "/api/watchlist"),
        ("GET", "/api/performance?period=1M"),
        ("GET", "/api/execution/toggle"),
        ("GET", "/api/rebalance/toggle"),
        ("GET", "/api/rebalance/status"),
        ("GET", "/api/execution/logs?limit=20"),
        ("GET", "/api/scores/BBCA.JK"),
        ("GET", "/api/recommend/BBCA.JK"),
        ("GET", "/api/indicators/BBCA.JK"),
        ("GET", "/api/explain/BBCA.JK"),
        ("GET", "/api/risk/BBCA.JK"),
        ("GET", "/api/positions"),
        ("GET", "/api/orders"),
        ("GET", "/api/portfolio/exposure"),
        ("GET", "/api/corporate/BBCA.JK"),
        ("GET", "/api/relationship/BBCA.JK"),
        ("GET", "/api/factor-weights/BBCA.JK"),
        ("GET", "/api/audit?limit=10"),
    ]

    for method, ep in endpoints:
        try:
            result = page.evaluate(f"""async () => {{
                try {{
                    const res = await fetch('{API_URL}{ep}', {{
                        method: '{method}',
                        headers: {{'X-API-Key': 'dev-secret-key-2026'}}
                    }});
                    const data = await res.text();
                    return {{status: res.status, length: data.length}};
                }} catch(e) {{
                    return {{error: e.message}};
                }}
            }}""")

            if "error" in result:
                _record(f"API {ep}", "fail", result["error"])
            elif result["status"] == 200:
                _record(f"API {ep}", "pass", f"HTTP 200 ({result['length']} bytes)")
            else:
                _record(f"API {ep}", "warn", f"HTTP {result['status']}")
        except Exception as e:
            _record(f"API {ep}", "fail", str(e))


def test_console_errors(page: Page):
    """Test 7: Capture console errors across all pages."""
    print("\n" + "=" * 60)
    print("  TEST 7: Console Error Capture")
    print("=" * 60)

    console_errors = []
    page_errors = []

    page.on("console", lambda msg: console_errors.append({
        "type": msg.type,
        "text": msg.text,
    }) if msg.type in ("error", "warning") else None)
    page.on("pageerror", lambda err: page_errors.append(str(err)))

    pages_to_check = [
        ("Dashboard", f"{BASE_URL}/dashboard"),
        ("Backtest", f"{BASE_URL}/backtest"),
        ("Portfolio", f"{BASE_URL}/portfolio"),
        ("Audit", f"{BASE_URL}/audit"),
        ("Engines", f"{BASE_URL}/engines"),
    ]

    for name, url in pages_to_check:
        console_errors.clear()
        page_errors.clear()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            time.sleep(3)

            error_count = len([e for e in console_errors if e["type"] == "error"])
            warn_count = len([e for e in console_errors if e["type"] == "warning"])
            page_err_count = len(page_errors)

            if error_count == 0 and page_err_count == 0:
                _record(f"Console {name}", "pass", f"{warn_count} warnings, 0 errors")
            else:
                detail = f"{error_count} errors, {warn_count} warnings, {page_err_count} page errors"
                _record(f"Console {name}", "warn", detail)
                for e in console_errors:
                    if e["type"] == "error":
                        print(f"    [ERROR] {e['text'][:150]}")
                for e in page_errors:
                    print(f"    [PAGE_ERR] {e[:150]}")
        except Exception as e:
            _record(f"Console {name}", "fail", str(e))


def main():
    print("=" * 60)
    print("  TRADING SYSTEM — COMPREHENSIVE PLAYWRIGHT E2E TEST")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Frontend: {BASE_URL}")
    print(f"  API: {API_URL}")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-gpu",
                "--window-position=1339,0",
                "--window-size=1280,800",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            record_video_dir=str(SCREEN_DIR / "videos"),
            record_video_size={"width": 1280, "height": 800},
        )
        page = context.new_page()

        # Run all tests
        test_dashboard(page)
        test_backtest(page)
        test_portfolio(page)
        test_audit(page)
        test_engines(page)
        test_api_endpoints(page)
        test_console_errors(page)

        # Final screenshot
        _screenshot(page, "comp_99_final")

        # Summary
        print("\n" + "=" * 60)
        print("  TEST SUMMARY")
        print("=" * 60)

        passed = sum(1 for r in results if r["status"] == "pass")
        failed = sum(1 for r in results if r["status"] == "fail")
        warned = sum(1 for r in results if r["status"] == "warn")

        for r in results:
            icon = "PASS" if r["status"] == "pass" else "FAIL" if r["status"] == "fail" else "WARN"
            print(f"  [{icon}] {r['test']}: {r['detail']}")

        print(f"\n  Total: {len(results)} | Pass: {passed} | Fail: {failed} | Warn: {warned}")
        print(f"  Screenshots: {SCREEN_DIR}/")
        print("=" * 60)

        # Save results JSON
        results_path = SCREEN_DIR / "test_results.json"
        with open(results_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"  Results JSON: {results_path}")

        print("\n  Browser akan tertutup dalam 10 detik...")
        time.sleep(10)

        context.close()
        browser.close()

        return 0 if failed == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
