"""End-to-end simulation of the Trading System dashboard using Playwright."""

import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

SCREEN_DIR = Path(__file__).parent / "screenshots"
SCREEN_DIR.mkdir(parents=True, exist_ok=True)


BASE_URL = "http://localhost:3000"


@pytest.fixture
def dashboard_page(page: Page):
    page.goto(f"{BASE_URL}/dashboard")
    # Wait for the app shell
    expect(page.locator("h1")).to_contain_text("Trading System")
    return page


def _screenshot(page: Page, name: str):
    page.screenshot(path=str(SCREEN_DIR / f"{name}.png"), full_page=True)


def _wait_for_action(page: Page):
    # Wait until one of the supported actions appears
    page.locator("text=/BUY|HOLD|WATCHLIST|AVOID/").first.wait_for(timeout=30_000)


def test_dashboard_loads(dashboard_page: Page):
    _screenshot(dashboard_page, "01_dashboard_loaded")
    assert dashboard_page.locator("input[placeholder='Ticker (e.g. BBCA.JK)']").input_value() == "BBCA.JK"


def test_analyze_default_ticker(dashboard_page: Page):
    dashboard_page.locator("button:has-text('Analyze')").click()
    _wait_for_action(dashboard_page)
    _screenshot(dashboard_page, "02_bbcj_analyzed")

    recommendation = dashboard_page.locator("text=/BUY|HOLD|WATCHLIST|AVOID/").first
    expect(recommendation).to_be_visible()
    action = recommendation.text_content().strip()
    assert action in ("BUY", "HOLD", "WATCHLIST", "AVOID")

    # Factor score chart (Recharts SVG) should be present
    chart = dashboard_page.locator("svg.recharts-surface")
    assert chart.is_visible()


def test_change_ticker_and_analyze(dashboard_page: Page):
    input_locator = dashboard_page.locator("input[placeholder='Ticker (e.g. BBCA.JK)']")
    input_locator.fill("TLKM.JK")
    dashboard_page.locator("button:has-text('Analyze')").click()

    # Wait for ticker header to update
    page_ticker = dashboard_page.locator("text=/TLKM\\.JK/")
    expect(page_ticker).to_be_visible(timeout=30_000)

    # Wait for the Analyze button to return to idle (analysis done)
    dashboard_page.locator("button:has-text('Analyze')").wait_for(timeout=30_000)
    _screenshot(dashboard_page, "03_tlkm_analyzed")

    # If a recommendation is generated for TLKM, capture it; otherwise dashboard handles missing scores
    rec_locator = dashboard_page.locator("text=/BUY|HOLD|WATCHLIST|AVOID/")
    if rec_locator.count() > 0:
        action = rec_locator.first.text_content().strip()
        assert action in ("BUY", "HOLD", "WATCHLIST", "AVOID")


def test_api_proxy_reachable(dashboard_page: Page):
    # Verify the embedded monitor footer received data
    footer = dashboard_page.locator("footer").first
    expect(footer).to_contain_text(re.compile(r"Tickers|Scores|Status"))
