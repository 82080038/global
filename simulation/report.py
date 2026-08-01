"""Report generator — buat HTML report interaktif dari hasil simulasi.

Penggunaan:
    python -m simulation.report                          # baca JSON terbaru
    python -m simulation.report --file reports/sim_20250101_120000.json
    python -m simulation.report --latest                 # baca JSON terbaru + buka browser
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from simulation.config import REPORT_DIR


def _status_color(status: str) -> str:
    return {
        "pass": "#22c55e",
        "fail": "#ef4444",
        "warn": "#f59e0b",
        "skip": "#6b7280",
    }.get(status, "#6b7280")


def _status_icon(status: str) -> str:
    return {
        "pass": "&#10003;",
        "fail": "&#10007;",
        "warn": "&#9888;",
        "skip": "&#8679;",
    }.get(status, "?")


def _find_latest_json() -> Path | None:
    files = sorted(REPORT_DIR.glob("sim_*.json"), reverse=True)
    return files[0] if files else None


def generate_html(report_data: dict) -> str:
    summary = report_data.get("summary", {})
    modules = report_data.get("modules", {})
    results = report_data.get("results", [])
    ts = report_data.get("timestamp", "")
    elapsed = report_data.get("elapsed_seconds", 0)
    ticker = report_data.get("primary_ticker", "N/A")
    capital = report_data.get("capital", 0)

    # Group results by module
    by_module: dict[str, list] = {}
    for r in results:
        by_module.setdefault(r["module"], []).append(r)

    rows_html = []
    for mod, items in by_module.items():
        for r in items:
            color = _status_color(r["status"])
            icon = _status_icon(r["status"])
            detail = r.get("detail", "")
            rows_html.append(f"""
            <tr>
                <td><span class="badge" style="background:{color}">{icon}</span></td>
                <td>{r['module']}</td>
                <td>{r['test']}</td>
                <td>{detail}</td>
            </tr>""")

    module_cards = []
    for mod, counts in modules.items():
        total = sum(counts.values())
        pass_pct = (counts.get("pass", 0) / total * 100) if total > 0 else 0
        module_cards.append(f"""
        <div class="card">
            <h3>{mod}</h3>
            <div class="bar-container">
                <div class="bar bar-pass" style="width:{pass_pct}%"></div>
            </div>
            <p>{counts.get('pass', 0)}/{total} passed</p>
        </div>""")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Trading System Simulation Report</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #0f172a; color: #e2e8f0; padding: 24px; }}
h1 {{ font-size: 1.8rem; margin-bottom: 4px; }}
h2 {{ font-size: 1.3rem; margin: 24px 0 12px; }}
.meta {{ color: #94a3b8; font-size: 0.9rem; margin-bottom: 24px; }}
.summary {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
.stat {{ background: #1e293b; border-radius: 12px; padding: 16px 24px; min-width: 120px; text-align: center; }}
.stat .num {{ font-size: 2rem; font-weight: 700; }}
.stat .label {{ font-size: 0.8rem; color: #94a3b8; text-transform: uppercase; }}
.stat-pass .num {{ color: #22c55e; }}
.stat-fail .num {{ color: #ef4444; }}
.stat-warn .num {{ color: #f59e0b; }}
.stat-skip .num {{ color: #6b7280; }}
.stat-total .num {{ color: #38bdf8; }}
.modules {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; margin-bottom: 24px; }}
.card {{ background: #1e293b; border-radius: 10px; padding: 14px; }}
.card h3 {{ font-size: 0.95rem; margin-bottom: 8px; color: #38bdf8; }}
.card p {{ font-size: 0.85rem; color: #94a3b8; }}
.bar-container {{ background: #334155; border-radius: 4px; height: 6px; margin-bottom: 6px; }}
.bar {{ height: 100%; border-radius: 4px; }}
.bar-pass {{ background: #22c55e; }}
table {{ width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 12px; overflow: hidden; }}
th {{ background: #334155; padding: 10px 14px; text-align: left; font-size: 0.85rem; text-transform: uppercase; color: #94a3b8; }}
td {{ padding: 8px 14px; border-top: 1px solid #334155; font-size: 0.9rem; }}
tr:hover {{ background: #334155; }}
.badge {{ display: inline-block; width: 24px; height: 24px; border-radius: 50%; text-align: center; line-height: 24px; font-weight: 700; color: #fff; font-size: 0.75rem; }}
</style>
</head>
<body>
<h1>Trading System &mdash; Simulation Report</h1>
<div class="meta">
    {ts} &middot; Ticker: <b>{ticker}</b> &middot; Capital: Rp {capital:,.0f} &middot; Elapsed: {elapsed}s
</div>

<div class="summary">
    <div class="stat stat-total"><div class="num">{summary.get('total', 0)}</div><div class="label">Total</div></div>
    <div class="stat stat-pass"><div class="num">{summary.get('pass', 0)}</div><div class="label">Pass</div></div>
    <div class="stat stat-fail"><div class="num">{summary.get('fail', 0)}</div><div class="label">Fail</div></div>
    <div class="stat stat-warn"><div class="num">{summary.get('warn', 0)}</div><div class="label">Warn</div></div>
    <div class="stat stat-skip"><div class="num">{summary.get('skip', 0)}</div><div class="label">Skip</div></div>
</div>

<h2>Module Breakdown</h2>
<div class="modules">
    {''.join(module_cards)}
</div>

<h2>Detailed Results</h2>
<table>
<thead><tr><th></th><th>Module</th><th>Test</th><th>Detail</th></tr></thead>
<tbody>
    {''.join(rows_html)}
</tbody>
</table>

</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Generate HTML report from simulation JSON")
    parser.add_argument("--file", default=None, help="Path to simulation JSON file")
    parser.add_argument("--latest", action="store_true", help="Use latest JSON and open in browser")
    args = parser.parse_args()

    if args.file:
        json_path = Path(args.file)
    else:
        json_path = _find_latest_json()

    if not json_path or not json_path.exists():
        print("No simulation JSON found. Run `python -m simulation.run_all` first.")
        return 1

    print(f"Reading: {json_path}")
    with open(json_path) as f:
        data = json.load(f)

    html = generate_html(data)
    html_path = json_path.with_suffix(".html")
    with open(html_path, "w") as f:
        f.write(html)
    print(f"HTML report: {html_path}")

    if args.latest:
        import webbrowser
        webbrowser.open(f"file://{html_path.resolve()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
