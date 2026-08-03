# Project Context — Trading System

## Overview

- **Project**: `trading-system` (Indonesian stocks / IDX decision support)
- **Version**: `0.1.11`
- **Language**: Python 3.10+ (target 3.11)
- **Repository root**: `/opt/lampp/htdocs/global`
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
- **Path**: `data/trading_system.db`
- **Schema migrations**: Alembic (`alembic/versions/0001_initial.py`, `0002_d1_d31_tables.py`)
- **Tables**: 33
- **Default tickers**: `BBCA.JK`, `TLKM.JK`, `ASII.JK`, `UNVR.JK`, `BMRI.JK`

### Snapshot (Aug 2, 2026)

These row counts are historical; query the database for current values.

| Table | Rows |
|-------|------|
| `ohlcv` | 2,035,881 |
| `technical_indicators` | 871,324 |
| `fundamental_data` | 131,292 |
| `foreign_flow` | 76,705 |
| `news` | 50,921 |
| `pattern_analysis` | 50,053 |
| `corporate_actions` | 16,310 |
| `dividends` | 11,173 |
| `scores` | 8,579 |
| `audit_log` | 3,092 |
| `macro_data` | 11,815 |
| `instrument_master` | 977 tickers |

## Runtime Configuration

Key defaults (see `.env` / `.env.example` for current values):

- `TRADING_CAPITAL`: Rp 100,000,000
- `RISK_PER_TRADE`: `1%`
- `EXIT_CONVICTION_THRESHOLD`: `40`
- `auto_trade_enabled`: `false`
- API key set for dev mode; CORS allows `localhost:3000`

## Development Conventions

- **Formatter / linter**: `ruff` (`pyproject.toml`)
  - `line-length = 120`
  - `target-version = "py311"`
  - Selected rules: `E`, `F`, `W`, `I`, `UP`, `B`, `SIM`
- **Type checking**: `mypy` with `python_version = "3.11"`
- **Tests**: `pytest` under `tests/unit/`
- **Coverage**: minimum `50%` (`fail_under = 50` in `pyproject.toml`)
- **E2E tests**: Playwright in `tests/e2e/`

## CLI Entry Points

`src/trading_system/cli.py` exposes subcommands including:

- `fetch`
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
