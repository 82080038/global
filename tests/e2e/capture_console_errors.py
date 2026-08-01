"""Capture all browser console errors and warnings during page navigation."""

from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:3000"
API_URL = "http://localhost:8000"
SCREEN_DIR = Path(__file__).parent / "screenshots"


def main():
    console_messages = []
    page_errors = []
    request_failures = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        # Capture console messages
        page.on("console", lambda msg: console_messages.append({
            "type": msg.type,
            "text": msg.text,
            "url": msg.location.get("url", "") if hasattr(msg, "location") else "",
        }))

        # Capture page errors (uncaught exceptions)
        page.on("pageerror", lambda err: page_errors.append({
            "message": str(err),
            "stack": err.stack if hasattr(err, "stack") else "",
        }))

        # Capture request failures
        page.on("requestfailed", lambda req: request_failures.append({
            "url": req.url,
            "method": req.method,
            "failure": req.failure if hasattr(req, "failure") else "",
        }))

        pages = [
            ("Dashboard", f"{BASE_URL}/dashboard"),
            ("Backtest", f"{BASE_URL}/backtest"),
            ("Portfolio", f"{BASE_URL}/portfolio"),
            ("Audit", f"{BASE_URL}/audit"),
            ("Engines", f"{BASE_URL}/engines"),
        ]

        for name, url in pages:
            print(f"\n{'='*60}")
            print(f"  Navigating to: {name} ({url})")
            print(f"{'='*60}")
            console_messages.clear()
            page_errors.clear()
            request_failures.clear()

            page.goto(url, wait_until="networkidle", timeout=30_000)
            time.sleep(3)

            # Try to trigger analyze on dashboard
            if "dashboard" in url:
                try:
                    page.locator("button:has-text('Analyze')").click()
                    time.sleep(5)
                except Exception:
                    pass

            # Try to run backtest
            if "backtest" in url:
                try:
                    page.locator("button:has-text('Run Backtest')").click()
                    time.sleep(5)
                except Exception:
                    pass

            print(f"\n--- Console Messages ({len(console_messages)}) ---")
            for msg in console_messages:
                emoji = {"error": "ERROR", "warning": "WARN", "info": "INFO", "log": "LOG", "debug": "DBG"}.get(msg["type"], msg["type"])
                print(f"  [{emoji}] {msg['text'][:200]}")

            print(f"\n--- Page Errors ({len(page_errors)}) ---")
            for err in page_errors:
                print(f"  [ERROR] {err['message'][:200]}")
                if err["stack"]:
                    print(f"    Stack: {err['stack'][:300]}")

            print(f"\n--- Request Failures ({len(request_failures)}) ---")
            for fail in request_failures:
                print(f"  [FAIL] {fail['method']} {fail['url'][:120]} → {fail.get('failure', '')}")

        # Also check API health
        print(f"\n{'='*60}")
        print(f"  API Health Check")
        print(f"{'='*60}")
        try:
            response = page.evaluate("""async () => {
                const res = await fetch('http://localhost:8000/api/health');
                return {status: res.status, ok: res.ok};
            }""")
            print(f"  /api/health: {response}")
        except Exception as e:
            print(f"  /api/health: FAILED - {e}")

        # Check specific API endpoints
        endpoints = [
            "/api/health",
            "/api/monitor",
            "/api/tickers",
            "/api/watchlist",
            "/api/performance?period=1M",
            "/api/execution/toggle",
            "/api/rebalance/toggle",
            "/api/rebalance/status",
            "/api/execution/logs?limit=20",
            "/api/scores/BBCA.JK",
            "/api/recommend/BBCA.JK",
            "/api/indicators/BBCA.JK",
            "/api/explain/BBCA.JK",
        ]

        print(f"\n--- API Endpoint Status ---")
        for ep in endpoints:
            try:
                result = page.evaluate(f"""async () => {{
                    try {{
                        const res = await fetch('http://localhost:8000{ep}');
                        const data = await res.text();
                        return {{status: res.status, length: data.length, preview: data.substring(0, 100)}};
                    }} catch(e) {{
                        return {{error: e.message}};
                    }}
                }}""")
                if "error" in result:
                    print(f"  [FAIL] {ep}: {result['error']}")
                else:
                    status = "OK" if result["status"] == 200 else f"HTTP {result['status']}"
                    print(f"  [{status}] {ep} ({result['length']} bytes)")
            except Exception as e:
                print(f"  [FAIL] {ep}: {e}")

        print(f"\n{'='*60}")
        print(f"  DONE — Browser tertutup dalam 5 detik")
        print(f"{'='*60}")
        time.sleep(5)
        browser.close()


if __name__ == "__main__":
    main()
