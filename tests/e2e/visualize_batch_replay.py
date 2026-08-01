"""Playwright visualization for batch replay results — comparison across all tickers.

Menampilkan dashboard perbandingan semua ticker yang sudah di-replay,
dengan summary table dan equity curve comparison.

Penggunaan:
    ./venv/bin/python tests/e2e/visualize_batch_replay.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:3000"
SCREEN_DIR = Path(__file__).parent / "screenshots"
RESULTS_DIR = Path(__file__).resolve().parents[2] / "scripts" / "replay_results"


def main():
    # Load all results
    summary_file = RESULTS_DIR / "summary.json"
    if not summary_file.exists():
        print(f"ERROR: {summary_file} not found. Run batch_replay.py first.")
        return

    with open(summary_file) as f:
        results = json.load(f)

    # Sort by return
    results.sort(key=lambda x: x.get("total_return_pct", -999), reverse=True)

    print("=" * 70)
    print("  BATCH REPLAY VISUALIZATION")
    print("=" * 70)
    print(f"  Tickers: {len(results)}")
    for r in results:
        ret = r.get("total_return_pct", 0)
        print(f"    {r['ticker']:<12} {ret:+.2f}%")
    print("=" * 70)

    # Build comparison HTML
    rows_html = ""
    for i, r in enumerate(results):
        ret = r.get("total_return_pct", 0)
        ret_color = "#4ecca3" if ret >= 0 else "#e94560"
        trades = f"{r.get('n_buys', 0)}B/{r.get('n_sells', 0)}S"
        sl_tp_ts = f"{r.get('n_stop_loss', 0)}/{r.get('n_take_profit', 0)}/{r.get('n_trailing_stop', 0)}"
        bg = "rgba(255,255,255,0.03)" if i % 2 == 0 else "transparent"
        rows_html += f"""
        <tr style="background:{bg};">
          <td style="padding:8px 12px;font-weight:bold;color:#e94560;">{r['ticker']}</td>
          <td style="padding:8px 12px;text-align:right;color:{ret_color};font-weight:bold;">{ret:+.2f}%</td>
          <td style="padding:8px 12px;text-align:right;">Rp {r.get('final_equity', 0):,.0f}</td>
          <td style="padding:8px 12px;text-align:right;">{r.get('sharpe_ratio', 0):.4f}</td>
          <td style="padding:8px 12px;text-align:right;">{r.get('max_drawdown_pct', 0):.2f}%</td>
          <td style="padding:8px 12px;text-align:center;">{trades}</td>
          <td style="padding:8px 12px;text-align:center;font-size:11px;">{sl_tp_ts}</td>
          <td style="padding:8px 12px;text-align:right;">{r.get('n_trading_days', 0)}</td>
        </tr>"""

    # Build equity curve chart data from individual results
    equity_data = {}
    for r in results:
        ticker = r["ticker"]
        result_file = RESULTS_DIR / f"replay_{ticker.replace('.', '_')}.json"
        if result_file.exists():
            with open(result_file) as f:
                detail = json.load(f)
            curve = detail.get("equity_curve", [])
            if curve:
                equity_data[ticker] = [(e["date"], e["equity"]) for e in curve]

    # Build chart SVG (simple line chart)
    if equity_data:
        all_dates = set()
        for curve in equity_data.values():
            for date, _ in curve:
                all_dates.add(date)
        all_dates = sorted(all_dates)

        chart_width = 1200
        chart_height = 400
        margin = 60
        plot_w = chart_width - 2 * margin
        plot_h = chart_height - 2 * margin

        # Find min/max equity
        all_equities = [e for curve in equity_data.values() for _, e in curve]
        min_eq = min(all_equities) * 0.99
        max_eq = max(all_equities) * 1.01

        # Date to x mapping
        n_dates = len(all_dates)
        def date_to_x(date):
            idx = all_dates.index(date) if date in all_dates else 0
            return margin + (idx / max(n_dates - 1, 1)) * plot_w

        def equity_to_y(eq):
            return margin + plot_h - ((eq - min_eq) / (max_eq - min_eq)) * plot_h

        # Colors for each ticker
        colors = ["#e94560", "#4ecca3", "#3b82f6", "#f59e0b", "#a855f7", "#06b6d4", "#ec4899", "#84cc16"]

        paths = ""
        legend = ""
        for i, (ticker, curve) in enumerate(equity_data.items()):
            color = colors[i % len(colors)]
            if len(curve) < 2:
                continue
            points = " ".join(f"{date_to_x(d):.1f},{equity_to_y(e):.1f}" for d, e in curve)
            paths += f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2" opacity="0.85"/>'
            legend += f'<span style="color:{color};margin-right:15px;font-size:12px;">● {ticker}</span>'

        # Grid lines
        grid = ""
        for pct in [0, 25, 50, 75, 100]:
            y = margin + (pct / 100) * plot_h
            eq_val = max_eq - (pct / 100) * (max_eq - min_eq)
            grid += f'<line x1="{margin}" y1="{y:.0f}" x2="{chart_width-margin}" y2="{y:.0f}" stroke="#27272a" stroke-width="1"/>'
            grid += f'<text x="{margin-10}" y="{y+4:.0f}" fill="#52525b" font-size="10" text-anchor="end">Rp {eq_val/1e6:.1f}M</text>'

        # X-axis labels (first, middle, last date)
        x_labels = ""
        if all_dates:
            for label_idx in [0, n_dates // 4, n_dates // 2, 3 * n_dates // 4, n_dates - 1]:
                if label_idx < len(all_dates):
                    d = all_dates[label_idx]
                    x = date_to_x(d)
                    x_labels += f'<text x="{x:.0f}" y="{chart_height-margin+20}" fill="#52525b" font-size="10" text-anchor="middle">{d}</text>'

        chart_svg = f"""
        <svg width="{chart_width}" height="{chart_height}" style="background:#111827;border-radius:8px;">
          {grid}
          {paths}
          {x_labels}
          <text x="{chart_width//2}" y="30" fill="#a1a1aa" font-size="14" text-anchor="middle" font-weight="bold">Equity Curve Comparison (Rp 10M initial capital, 12 months)</text>
        </svg>
        <div style="margin:10px 0;padding:8px;background:#111827;border-radius:4px;">{legend}</div>
        """
    else:
        chart_svg = "<p>No equity curve data available</p>"

    # Build full HTML page
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>Batch Replay Results</title>
      <style>
        body {{ background:#0a0a0f; color:#e0e0e0; font-family:'Courier New',monospace; padding:20px; margin:0; }}
        h1 {{ color:#e94560; border-bottom:2px solid #0f3460; padding-bottom:10px; }}
        h2 {{ color:#a1a1aa; margin-top:30px; }}
        table {{ width:100%; border-collapse:collapse; margin:15px 0; font-size:13px; }}
        th {{ background:#0f3460; color:#e0e0e0; padding:10px 12px; text-align:left; font-weight:bold; }}
        th:nth-child(n+2) {{ text-align: center; }}
        td {{ padding:8px 12px; border-bottom:1px solid #1a1a2e; }}
        .summary {{ display:flex; gap:20px; margin:20px 0; }}
        .card {{ background:#111827; padding:15px; border-radius:8px; flex:1; text-align:center; }}
        .card .label {{ color:#52525b; font-size:11px; text-transform:uppercase; }}
        .card .value {{ font-size:24px; font-weight:bold; margin-top:5px; }}
        .positive {{ color:#4ecca3; }}
        .negative {{ color:#e94560; }}
        .chart-container {{ margin:20px 0; overflow-x:auto; }}
      </style>
    </head>
    <body>
      <h1>Batch Replay Simulation Results</h1>
      <p style="color:#52525b;">Full pipeline replay: TechnicalAnalysis → DecisionEngine → RiskEngine → CostModel → Portfolio | Capital: Rp 10,000,000 | Period: 12 months</p>

      <div class="summary">
        <div class="card">
          <div class="label">Tickers Tested</div>
          <div class="value">{len(results)}</div>
        </div>
        <div class="card">
          <div class="label">Profitable</div>
          <div class="value positive">{sum(1 for r in results if r.get('total_return_pct', 0) > 0)}</div>
        </div>
        <div class="card">
          <div class="label">Break-even</div>
          <div class="value">{sum(1 for r in results if r.get('total_return_pct', 0) == 0)}</div>
        </div>
        <div class="card">
          <div class="label">Loss</div>
          <div class="value negative">{sum(1 for r in results if r.get('total_return_pct', 0) < 0)}</div>
        </div>
        <div class="card">
          <div class="label">Best Return</div>
          <div class="value positive">{max(r.get('total_return_pct', 0) for r in results):+.2f}%</div>
        </div>
        <div class="card">
          <div class="label">Worst Return</div>
          <div class="value negative">{min(r.get('total_return_pct', 0) for r in results):+.2f}%</div>
        </div>
      </div>

      <h2>Performance Comparison</h2>
      <table>
        <thead>
          <tr>
            <th>Ticker</th>
            <th style="text-align:right;">Return</th>
            <th style="text-align:right;">Final Equity</th>
            <th style="text-align:right;">Sharpe</th>
            <th style="text-align:right;">Max DD</th>
            <th style="text-align:center;">Trades</th>
            <th style="text-align:center;">SL/TP/TS</th>
            <th style="text-align:right;">Days</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>

      <h2>Equity Curve Comparison</h2>
      <div class="chart-container">
        {chart_svg}
      </div>

      <h2>Trade Details</h2>
      <table>
        <thead>
          <tr>
            <th>Ticker</th>
            <th style="text-align:right;">Realized PnL</th>
            <th style="text-align:right;">Total Fees</th>
            <th style="text-align:center;">Stop Loss</th>
            <th style="text-align:center;">Take Profit</th>
            <th style="text-align:center;">Trailing Stop</th>
          </tr>
        </thead>
        <tbody>
          {"".join(f'''
          <tr style="background:{"rgba(255,255,255,0.03)" if i%2==0 else "transparent"};">
            <td style="padding:8px 12px;font-weight:bold;color:#e94560;">{r["ticker"]}</td>
            <td style="padding:8px 12px;text-align:right;color:{"#4ecca3" if r.get("total_realized_pnl",0)>=0 else "#e94560"};">Rp {r.get("total_realized_pnl",0):,.0f}</td>
            <td style="padding:8px 12px;text-align:right;">Rp {r.get("total_fees",0):,.0f}</td>
            <td style="padding:8px 12px;text-align:center;color:#e94560;">{r.get("n_stop_loss",0)}</td>
            <td style="padding:8px 12px;text-align:center;color:#4ecca3;">{r.get("n_take_profit",0)}</td>
            <td style="padding:8px 12px;text-align:center;color:#f59e0b;">{r.get("n_trailing_stop",0)}</td>
          </tr>''' for i, r in enumerate(results))}
        </tbody>
      </table>

      <p style="color:#52525b;font-size:11px;margin-top:30px;">
        Generated by replay_simulation.py using full application pipeline:<br>
        TechnicalAnalysisEngine → DecisionEngine (conviction + regime filter + AI weights) → RiskEngine (ATR-based SL/TP + position sizing) → CostModel IDX (fees + levy + slippage + tax) → Portfolio tracking (equity + PnL + snapshots)
      </p>
    </body>
    </html>
    """

    # Save HTML
    html_file = SCREEN_DIR / "batch_replay_report.html"
    html_file.write_text(html)
    print(f"  HTML report: {html_file}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        # Load the HTML report
        page.set_content(html, wait_until="networkidle")
        time.sleep(2)

        # Screenshot
        screenshot_path = SCREEN_DIR / "batch_replay_summary.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"  Screenshot: {screenshot_path}")

        # Also visit dashboard for the best performer
        best_ticker = results[0]["ticker"]
        print(f"\n  Visiting dashboard for best performer: {best_ticker}")
        page.goto(f"{BASE_URL}/dashboard")
        page.wait_for_selector("h1", timeout=15_000)
        try:
            ticker_input = page.locator("input[placeholder='Ticker (e.g. BBCA.JK)']")
            if ticker_input.count() > 0:
                ticker_input.fill(best_ticker)
                page.locator("button:has-text('Analyze')").click()
                page.locator("text=/BUY|HOLD|WATCHLIST|AVOID|SELL/").first.wait_for(timeout=30_000)
                time.sleep(2)
        except Exception:
            pass
        page.screenshot(path=str(SCREEN_DIR / "batch_replay_best_ticker.png"), full_page=True)
        print(f"  Screenshot: {SCREEN_DIR / 'batch_replay_best_ticker.png'}")

        print("\n" + "=" * 70)
        print("  VISUALIZATION COMPLETE")
        print(f"  Browser tertutup dalam 15 detik...")
        print("=" * 70)
        time.sleep(15)

        context.close()
        browser.close()


if __name__ == "__main__":
    main()
