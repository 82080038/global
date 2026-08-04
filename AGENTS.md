# Project Context — Trading System

## Overview

- **Project**: `trading-system` (Indonesian stocks / IDX decision support)
- **Version**: `0.1.11`
- **Language**: Python 3.10+ (target 3.11, tested on 3.12)
- **Repository root** (Windows): `C:\xampp\htdocs\global`
- **Repository root** (Linux): `/home/petrick/projects/global`
- **Virtualenv**: `.venv/` in repo root
- **Backend**: `src/trading_system/` (setuptools package under `src`)
- **Frontend**: `frontend/` (Next.js + TypeScript; see `frontend/AGENTS.md` for Next.js-specific rules)
- **CLI**: `src/trading_system/cli.py`
- **API**: `src/trading_system/api/app.py`

## Module Map

| Module | Purpose |
|--------|---------|
| `src/trading_system/data/` | Acquisition (Yahoo Finance), SQLite storage/validation/seeder, archive, rate limiting, legacy import, IDX scraping |
| `src/trading_system/analysis/` | Technical, fundamental, macro, global market, pipeline, relationship, regime, cross-asset, lead-lag, factor engine, alpha composer/validation, attribution, manipulation, no-trade, order-book, red flags, screener/factor screener, world monitor, enhanced regime, advanced technical |
| `src/trading_system/sentiment/` | Engine (Indonesian NLP), foreign flow, broker summary, social media (Reddit/X), Google Trends |
| `src/trading_system/decision/` | `engine.py` — multi-factor weighted scoring |
| `src/trading_system/risk/` | VaR/CVaR, position sizing, drawdown, Kelly, correlation sizing, costs, expectancy, enhanced risk |
| `src/trading_system/execution/` | Automated robot trader, broker adapter (Mock + Sinarmas/BNI stubs), paper/real execution, tax, interface |
| `src/trading_system/portfolio/` | Engine, performance, rebalancer |
| `src/trading_system/ai_learning/` | LR weight optimization, deep learning, ensemble, labeling, model registry, purged TSS, walk-forward |
| `src/trading_system/backtest/` | Engine, strategies, metrics (Monte Carlo, Walk-Forward) |
| `src/trading_system/xai/` | Explainable AI engine (narrative + top factors) |
| `src/trading_system/monitoring/` | System health monitor |
| `src/trading_system/paper_trading/` | Paper trading simulator |
| `src/trading_system/corporate/` | Corporate actions (splits, dividends) |
| `src/trading_system/utils/` | Telegram notifier |

## Scoring Weights

The default multi-factor decision weights in `decision/engine.py`:

- Technical: `20%`
- Fundamental: `25%`
- Macro: `15%`
- Global market: `15%`
- Relationship: `10%`
- Sentiment: `15%`

## Database

- **Engine**: SQLite in WAL mode
- **Path**: `data/trading_system.db` (~460 MB)
- **Schema migrations**: Alembic (`alembic/versions/0001_initial.py`, `0002_d1_d31_tables.py`, `0003_ipo_suspension_delisting.py`)
- **Total tables**: 41 (query DB for current count)
- **Default tickers**: `BBCA.JK`, `TLKM.JK`, `ASII.JK`, `UNVR.JK`, `BMRI.JK`

### Instrument Classification

- **Equity stocks (saham)**: `asset_class = 'equity'` — 928 active listed, 40 delisted
- **Non-equity reference**: forex (4), index (12), commodity (4), ETF (4) — used as macro/global reference, NOT for trading signals
- **Downstream engines** must filter `is_active = 1 AND asset_class = 'equity'` to process only listed saham

### Parquet Storage

- **Raw dir**: `DATA_RAW_DIR` env var (default: `/media/petrick/Parquet/trading_data/raw`) — ~1222 files
- **Archive dir**: `DATA_ARCHIVE_DIR` env var (default: `/media/petrick/Parquet/trading_data/archive`) — ~1027 files
- **Sync status**: Check via `/api/storage-info` endpoint

### Snapshot (Aug 4, 2026)

These row counts are historical; query the database for current values.

| Table | Rows |
|-------|------|
| `ohlcv` | 2,904,119 |
| `foreign_flow` | 103,046 |
| `broker_flow` | 15,830 |
| `macro_data` | 10,036 |
| `scores` | 9,830 |
| `technical_indicators` | 11,136 |
| `relationship_matrix` | 12,077 |
| `corporate_actions` | 6,365 |
| `dividends` | 5,974 |
| `audit_log` | 3,125 |
| `pattern_analysis` | 2,386 |
| `instrument_master` | 992 |
| `fundamental_data` | 991 |
| `stock_personality` | 944 |
| `fear_greed` | 466 |
| `market_calendar` | 365 |
| `watchlist` | 359 |
| `esg_scores` | 164 |
| `external_events` | 119 |
| `news` | 110 |
| `policy_events` | 179 |

## API

- **Entry point**: `src/trading_system/api/app.py`
- **Total endpoints**: 94 (REST + WebSocket)
- **Auth**: API key via `X-API-Key` header, `API_KEY` env var
- **Key endpoints**: `/api/data-overview`, `/api/instrument-status`, `/api/storage-info`, `/api/market-status`, `/api/market-calendar`, `/api/health`, `/api/monitor`, `/api/recommend/{ticker}`, `/api/explain/{ticker}`, `/api/backtest`

## Frontend

- **Location**: `frontend/`
- **Current state**: Single-page application — Data Inspection Dashboard only at `/`
- **All other pages removed** (dashboard, backtest, engines, portfolio, audit, replay, simulation, schedule)
- **Layout**: `frontend/app/components/TerminalLayout.tsx` — sidebar with only "Data Inspection" link
- **API layer**: `frontend/app/lib/api.ts` — `safeApiFetch()` with `X-API-Key` header injection
- **Section IDs**: Every major section in `page.tsx` has unique `id` attribute for Playwright selectors

## GPU / CUDA

- **Hardware**: 2x NVIDIA GeForce GTX 1050 Ti (Pascal GP107, compute capability 6.1, 4 GB VRAM each)
- **Driver**: NVIDIA 580.173.02, CUDA Runtime 13.0
- **Toolkit**: nvcc 12.0.140, cuDNN 8.x (system), cuDNN 9.1 (torch wheel)
- **GPU 0**: used by Xorg/GNOME display — prefer `cuda:1` for compute workloads
- **GPU 1**: free for ML compute
- **PyTorch**: 2.5.1+cu121 installed in `.venv` (auto-detects CUDA, prefers `cuda:1`)
- **Install extra**: `pip install -e ".[gpu]" --index-url https://download.pytorch.org/whl/cu121`
- **VRAM constraint**: 4 GB/GPU — keep batch_size <= 64 and hidden dim <= 256
- **No Tensor Cores** (Pascal) — FP32 is the primary path; FP16 acceleration is limited
- **Used by**: `src/trading_system/ai_learning/deep_learning.py` (LSTM, backend priority: torch > tensorflow > sklearn)
- **Monitor**: `nvidia-smi` (allowed in `.devin/config.json`)

## Runtime Configuration

Key defaults (see `.env` / `.env.example` for current values):

- `TRADING_CAPITAL`: Rp 100,000,000
- `RISK_PER_TRADE`: `1%`
- `EXIT_CONVICTION_THRESHOLD`: `40`
- `auto_trade_enabled`: `false`
- `API_KEY`: `dev-secret-key-2026` (dev mode)
- CORS allows `localhost:3000`

## Development Conventions

- **Formatter / linter**: `ruff` (`pyproject.toml`)
  - `line-length = 120`
  - `target-version = "py311"`
  - Selected rules: `E`, `F`, `W`, `I`, `UP`, `B`, `SIM`
- **Type checking**: `mypy` with `python_version = "3.11"`
- **Tests**: `pytest` under `tests/unit/` — 45 test files, 600+ tests
- **Coverage**: minimum `50%` (`fail_under = 50` in `pyproject.toml`)
- **E2E tests**: Playwright in `tests/e2e/`
- **Virtualenv**: `.venv/` — use `.venv/bin/python`, `.venv/bin/ruff`, `.venv/bin/pytest`, `.venv/bin/alembic`

## CLI Entry Points

`src/trading_system/cli.py` exposes subcommands including:

- `fetch`
- `fetch-idx-foreign-flow`
- `fetch-idx-broker-flow`
- `list`
- `compute-scores`
- `corporate-actions`
- `update-adjusted-close`
- `import-legacy`
- `relationship`
- `recommend`
- `explain`
- `monitor`
- `paper-trade`
- `backtest`
- `execution`
- `test-e2e`
- `schedule`
