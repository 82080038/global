"""Record a headed Playwright session to a video file."""

import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT_DIR = Path(__file__).parent / "demo_gif"
OUT_DIR.mkdir(exist_ok=True)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--no-sandbox"])
        context = browser.new_context(
            record_video_dir=str(OUT_DIR),
            record_video_size={"width": 1280, "height": 720},
            viewport={"width": 1280, "height": 720},
        )
        page = context.new_page()

        page.goto("http://localhost:3000/dashboard")
        page.wait_for_selector("h1:has-text('Trading System')", timeout=30_000)

        # --- BBCA.JK ---
        page.locator("button:has-text('Analyze')").click()
        page.locator("text=/BUY|HOLD|WATCHLIST|AVOID/").first.wait_for(timeout=30_000)
        time.sleep(1.5)

        # --- TLKM.JK ---
        page.locator("input[placeholder='Ticker (e.g. BBCA.JK)']").fill("TLKM.JK")
        page.locator("button:has-text('Analyze')").click()
        page.locator("text=/TLKM\\.JK/").first.wait_for(timeout=30_000)
        time.sleep(1.5)

        context.close()
        browser.close()

        video = page.video
        if video:
            print(video.path())


if __name__ == "__main__":
    main()
