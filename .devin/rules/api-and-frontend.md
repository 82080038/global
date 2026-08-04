# API & Frontend Conventions

## Backend (FastAPI)

- **Entry point**: `src/trading_system/api/app.py`
- **Total endpoints**: 94 (REST + WebSocket)
- **Auth**: API key via `X-API-Key` header, `API_KEY` env var (optional in dev, required in production)
- **CORS**: configured via `CORS_ORIGINS` env var (default: `localhost:3000`)
- **Rate limiting**: `RATE_LIMIT_MAX` requests per IP per 60 seconds
- **Key endpoint groups**:
  - `/api/data-overview` — data completeness summary
  - `/api/instrument-status` — listed vs delisted equity vs non-equity (forex/index/commodity/ETF)
  - `/api/storage-info` — database path/size, parquet sync status, render schedule
  - `/api/market-status` — IDX market session, trading hours, holidays
  - `/api/market-calendar` — calendar, render log, data freshness
  - `/api/health` — source health per data source
  - `/api/monitor` — system health, alerts, ticker list
  - `/api/data/{category}` — OHLCV, indicators, fundamentals per ticker
  - `/api/recommend/{ticker}`, `/api/explain/{ticker}` — decision + XAI
  - `/api/backtest`, `/api/backtest/monte-carlo`, `/api/backtest/walk-forward`
  - `/api/positions`, `/api/orders`, `/api/portfolio/exposure`
  - `/api/execution/run`, `/api/execution/toggle`, `/api/rebalance/toggle`
  - `/api/extended/*` — 15 endpoints for MySQL-imported tables

## Frontend (Next.js + TypeScript)

- **Location**: `frontend/`
- **See**: `frontend/AGENTS.md` for Next.js-specific rules
- **Current state**: Single-page application — Data Inspection Dashboard only
- **Pages**: Only `/` (root) — all other pages removed (dashboard, backtest, engines, portfolio, audit, replay, simulation, schedule)
- **Layout**: `frontend/app/components/TerminalLayout.tsx` — sidebar with only "Data Inspection" link
- **API layer**: `frontend/app/lib/api.ts` — `safeApiFetch()` with `X-API-Key` header injection
- **API base URL**: `NEXT_PUBLIC_API_BASE` env var (default: `http://localhost:8000`)
- **API key**: `NEXT_PUBLIC_API_KEY` must match backend `API_KEY`
- **Section IDs in page.tsx** (for Playwright selectors):
  - `#section-top-stats`, `#section-market-status`, `#section-instrument-status`
  - `#section-data-factors`, `#section-source-stale`, `#section-sector-breakdown`
  - `#section-asset-class`, `#section-storage-sync`, `#section-render-schedule`
  - Panels: `#panel-source-health`, `#panel-stale-tickers`, `#panel-database-info`, `#panel-parquet-info`, `#panel-render-log`, `#panel-render-recommendations`
  - `.stat-card[data-label='...']` for individual stat cards

## Guidelines

- Do not hardcode API URLs — use env vars.
- Do not expose API keys in client-side code unless via `NEXT_PUBLIC_*` vars.
- Follow existing patterns for endpoint registration and error handling.
- New endpoints must be added to the FastAPI app in `app.py` following the existing pattern.
- Frontend changes must use `safeApiFetch()` from `lib/api.ts` — never use raw `fetch()`.
- Every major section in `page.tsx` must have a unique `id` attribute for test selectors.
