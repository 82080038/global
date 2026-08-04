# Workflow: Data Inspection Dashboard

## Purpose
Verify data quality, completeness, and instrument classification via the Data Inspection Dashboard.

## Steps

### 1. Start servers (if not running)

```bash
# Backend
ENV=development API_KEY=dev-secret-key-2026 .venv/bin/uvicorn trading_system.api.app:app --port 8000 --log-level warning &

# Frontend
cd frontend && npm run dev &
```

### 2. Verify API endpoints

```bash
# Data overview
curl -s -H "X-API-Key: dev-secret-key-2026" http://localhost:8000/api/data-overview | python3 -m json.tool | head -20

# Instrument status (equity vs non-equity)
curl -s -H "X-API-Key: dev-secret-key-2026" http://localhost:8000/api/instrument-status | python3 -c "
import sys,json
d=json.load(sys.stdin)
s=d['summary']
print(f'Equity: {s[\"equity_active\"]} active, {s[\"equity_delisted\"]} delisted, {s[\"equity_active_without_ohlcv\"]} without data')
print(f'Non-equity: {s[\"non_equity_total\"]} total, {s[\"non_equity_without_ohlcv\"]} without data')
"

# Storage & sync
curl -s -H "X-API-Key: dev-secret-key-2026" http://localhost:8000/api/storage-info | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f'DB: {d[\"database\"][\"size_human\"]} at {d[\"database\"][\"path\"]}')
print(f'Parquet synced: {d[\"parquet\"][\"synced\"]}')
print(f'Render: {d[\"render\"][\"total_renders\"]} total, {d[\"render\"][\"ok\"]} ok, {d[\"render\"][\"failed\"]} failed')
"
```

### 3. Visual verification (Playwright)

```bash
.venv/bin/python -c "
from playwright.sync_api import sync_playwright
import os, time
os.environ['DISPLAY'] = ':1'
with sync_playwright() as p:
    b = p.chromium.launch(headless=False, args=['--no-sandbox','--disable-gpu','--window-position=1339,0','--window-size=1280,800'])
    ctx = b.new_context(viewport={'width':1280,'height':800})
    page = ctx.new_page()
    page.goto('http://localhost:3000/', wait_until='domcontentloaded', timeout=30000)
    page.wait_for_selector('#section-instrument-status', timeout=30000)
    time.sleep(5)
    page.screenshot(path='/tmp/data_inspection.png', full_page=True)
    print('Screenshot saved')
    b.close()
"
```

### 4. Check key sections

Verify these sections are visible and populated:
- `#section-top-stats` — 6 stat cards (Total Tickers, Total Rows, Completeness, Freshness, Date Range, Scores)
- `#section-market-status` — IDX session, open/close times, next open
- `#section-instrument-status` — Equity (928 listed, 0 without data) + Non-equity (24 reference, 4 without data)
- `#section-data-factors` — Completeness matrix per factor category
- `#section-source-stale` — Source health + stale tickers
- `#section-storage-sync` — Database path/size, Parquet sync status
- `#section-render-schedule` — Render log, next trading day, recommendations

### 5. Common issues

- **EURIDR=X / JPYIDR=X / ^LQ45 in "without data" warning**: These are non-equity (forex/index), not stocks. They should appear in the Non-Equity Reference table, NOT in the equity warning.
- **API returns 401**: Check `X-API-Key` header matches `API_KEY` in `.env`
- **Frontend blank**: Check `NEXT_PUBLIC_API_BASE` and `NEXT_PUBLIC_API_KEY` in `frontend/.env.local`
