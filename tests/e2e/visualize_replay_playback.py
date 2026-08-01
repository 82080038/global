"""Playwright visualization — record the replay playback process.

Membuka halaman /replay, memilih ticker, dan merekam playback
hari-demi-hari dengan Playwright video recording.

Penggunaan:
    ./venv/bin/python tests/e2e/visualize_replay_playback.py [--ticker BBCA.JK]
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:3000"
SCREEN_DIR = Path(__file__).parent / "screenshots"
SCREEN_DIR.mkdir(parents=True, exist_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="BBCA.JK")
    parser.add_argument("--speed", type=int, default=200, help="ms per day")
    args = parser.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--no-sandbox"])
        context = browser.new_context(
            viewport={"width": 1400, "height": 900},
            record_video_dir=str(SCREEN_DIR / "videos_replay"),
            record_video_size={"width": 1400, "height": 900},
        )
        page = context.new_page()

        print(f"[1] Opening /replay page...")
        page.goto(f"{BASE_URL}/replay", wait_until="networkidle", timeout=30_000)
        page.wait_for_selector("text=Replay Simulation", timeout=15_000)
        time.sleep(2)

        # Screenshot: initial state
        page.screenshot(path=str(SCREEN_DIR / "replay_01_initial.png"), full_page=True)
        print(f"  Screenshot: replay_01_initial.png")

        # Select ticker
        print(f"[2] Selecting ticker: {args.ticker}")
        ticker_btn = page.locator(f"button:has-text('{args.ticker}')")
        if ticker_btn.count() > 0:
            ticker_btn.click()
            # Wait for data to load
            page.wait_for_selector("text=PRICE & ACTION", timeout=15_000)
            time.sleep(2)

        # Screenshot: day 1
        page.screenshot(path=str(SCREEN_DIR / "replay_02_day1.png"), full_page=True)
        print(f"  Screenshot: replay_02_day1.png")

        # Set speed
        print(f"[3] Setting playback speed to {args.speed}ms/day")
        page.select_option("select", str(args.speed))
        time.sleep(1)

        # Click Play
        print(f"[4] Starting playback...")
        play_btn = page.locator("button:has-text('Play')")
        if play_btn.count() > 0:
            play_btn.click()

        # Record progress — take screenshots at key moments
        # Wait for some trades to happen
        # BBCA.JK has 262 days, first BUY around day 2-3
        # Let it play for ~30 seconds to see several days
        print(f"[5] Recording playback for 30 seconds...")
        time.sleep(10)
        page.screenshot(path=str(SCREEN_DIR / "replay_03_progress_10s.png"), full_page=True)
        print(f"  Screenshot: replay_03_progress_10s.png")

        time.sleep(10)
        page.screenshot(path=str(SCREEN_DIR / "replay_04_progress_20s.png"), full_page=True)
        print(f"  Screenshot: replay_04_progress_20s.png")

        # Pause and check current state
        pause_btn = page.locator("button:has-text('Pause')")
        if pause_btn.count() > 0:
            pause_btn.click()
        time.sleep(1)
        page.screenshot(path=str(SCREEN_DIR / "replay_05_paused.png"), full_page=True)
        print(f"  Screenshot: replay_05_paused.png")

        # Jump to end
        print(f"[6] Jumping to last day...")
        end_btn = page.locator("button:has-text('End')")
        if end_btn.count() > 0:
            end_btn.click()
        time.sleep(2)

        # Screenshot: final state
        page.screenshot(path=str(SCREEN_DIR / "replay_06_final.png"), full_page=True)
        print(f"  Screenshot: replay_06_final.png")

        # Now switch to ASII.JK (worst performer) to show comparison
        print(f"[7] Switching to ASII.JK (worst performer)...")
        asii_btn = page.locator("button:has-text('ASII.JK')")
        if asii_btn.count() > 0:
            asii_btn.click()
            page.wait_for_selector("text=PRICE & ACTION", timeout=15_000)
            time.sleep(2)
            page.screenshot(path=str(SCREEN_DIR / "replay_07_asii_day1.png"), full_page=True)
            print(f"  Screenshot: replay_07_asii_day1.png")

            # Jump to end
            end_btn = page.locator("button:has-text('End')")
            if end_btn.count() > 0:
                end_btn.click()
            time.sleep(2)
            page.screenshot(path=str(SCREEN_DIR / "replay_08_asii_final.png"), full_page=True)
            print(f"  Screenshot: replay_08_asii_final.png")

        # Switch to UNVR.JK (most active — 6 trades)
        print(f"[8] Switching to UNVR.JK (most active — 6 trades)...")
        unvr_btn = page.locator("button:has-text('UNVR.JK')")
        if unvr_btn.count() > 0:
            unvr_btn.click()
            page.wait_for_selector("text=PRICE & ACTION", timeout=15_000)
            time.sleep(2)

            # Play at fast speed
            page.select_option("select", "50")
            play_btn = page.locator("button:has-text('Play')")
            if play_btn.count() > 0:
                play_btn.click()
            print(f"  Playing UNVR.JK at turbo speed for 15 seconds...")
            time.sleep(15)

            pause_btn = page.locator("button:has-text('Pause')")
            if pause_btn.count() > 0:
                pause_btn.click()
            time.sleep(1)
            page.screenshot(path=str(SCREEN_DIR / "replay_09_unvr_progress.png"), full_page=True)
            print(f"  Screenshot: replay_09_unvr_progress.png")

            # Jump to end
            end_btn = page.locator("button:has-text('End')")
            if end_btn.count() > 0:
                end_btn.click()
            time.sleep(2)
            page.screenshot(path=str(SCREEN_DIR / "replay_10_unvr_final.png"), full_page=True)
            print(f"  Screenshot: replay_10_unvr_final.png")

        print(f"\n{'='*60}")
        print(f"  PLAYBACK VISUALIZATION COMPLETE")
        print(f"  Screenshots: {SCREEN_DIR}/")
        print(f"  Video: {SCREEN_DIR}/videos_replay/")
        print(f"{'='*60}")
        print(f"\n  Browser tertutup dalam 10 detik...")
        time.sleep(10)

        context.close()
        browser.close()


if __name__ == "__main__":
    main()
