# Changelog

Semua perubahan penting pada proyek ini didokumentasikan dalam file ini.

Format berdasarkan [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), dan proyek ini mengikuti [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] — 2026-07-31

### Added — Data Layer

- Yahoo Finance data acquisition dengan auto-retry dan rate limiting
- Data quality validator: gap detection, stale data, anomaly flagging, quality score 0-100
- SQLite storage dengan 12 tabel: ohlcv, source_health, audit_log, scores, relationship_matrix, corporate_actions, news, positions, orders, equity_snapshots, watchlist, ai_weights, daily_risk_metrics
- Pydantic data contracts: OHLCVRecord, DataSourceHealth, DataQualityReport
- Database seeder untuk testing
- Parquet export untuk raw/clean zone

### Added — Analysis Layer

- Technical Analysis Engine: RSI, MACD, MA20/50/200, Bollinger Bands, ADX, OBV
- Fundamental Analysis Engine: P/E, P/B, ROE, Debt/Equity, Dividend Yield, EPS growth
- Macro Economic Engine: proxy via US10Y, GOLD, OIL, USD/IDR, DXY; regime detection (easing/tightening/neutral/risk_off)
- Global Market Engine: correlation dengan S&P500, Nikkei225, CSI300, STOXX600
- Market Relationship Engine: rolling correlation, lag analysis, lead/lag matrix
- Analysis Pipeline: orchestration semua engine dengan parallel execution

### Added — Sentiment Layer

- NLP Sentiment Engine: RSS feed Bisnis.com, Kontan, CNBC Indonesia; Indonesian lexicon (40+ positive, 40+ negative words); fallback price/volume proxy
- Foreign Flow Sentiment: volume+price proxy untuk foreign accumulation/distribution
- Broker Summary Sentiment: smart money classification (CLSA, JPM, UBS, dll), retail broker detection
- Social Media Sentiment: Reddit (r/IndonesiaInvesting, r/saham), X/Twitter; Indonesian lexicon + emoji detection
- Google Trends Sentiment: search interest sebagai leading indicator, pytrends integration

### Added — Risk Layer

- Risk Engine: ATR-based position sizing, stop-loss (1.5×ATR), take-profit (2× stop distance), VaR 95/99, CVaR, slippage estimation, liquidity check
- Daily risk metrics disimpan ke database (VaR, CVaR, max drawdown, annualized volatility)

### Added — Portfolio Layer

- Portfolio Engine: generate orders dari recommendation, capital allocation
- Performance Analytics: equity curve, total return, Sharpe ratio, max drawdown, win rate, profit factor, average win/loss, daily snapshots
- Portfolio Rebalancer: target weights dari env var, drift detection, auto/manual rebalance, runtime toggle via API

### Added — Execution Layer

- Execution Engine: fee calculation (broker 0.15%, levy 0.00043%, PPh 0.1% sell), dynamic slippage, simulate fill, feasibility check
- Automated Execution Engine (Robot Trader): signal processing dari Decision Engine, position sizing dari Risk Engine, stop-loss/take-profit/trailing stop monitoring, daily loss limit circuit breaker, mode monitoring (default) vs mode eksekusi

### Added — Intelligence Layer

- Decision Engine: weighted scoring (technical 25%, fundamental 25%, macro 15%, global 15%, relationship 10%, sentiment 10%), BUY/HOLD/WATCHLIST/AVOID, conviction score
- XAI Engine: narrative explanation dalam Bahasa Indonesia, top factors, confidence interval
- AI Learning Engine: regime-specific weights, consistency-based adjustment, data coverage adjustment, Linear Regression training dari forward returns (scikit-learn)

### Added — Simulation & Testing

- Paper Trading Engine: simulate order dengan harga pasar, PnL tracking
- Backtest Engine: buy & hold, MA crossover, cost model (broker fee, levy, slippage, PPh)
- Backtest Metrics: Monte Carlo simulation, Walk-Forward analysis
- Monitoring Engine: system health, source status, alert detection

### Added — Corporate Actions

- Corporate Action Engine: split & dividend detection via yfinance, price adjustment, adj_factor calculation

### Added — API Layer

- FastAPI REST API: 30+ endpoints (system, data, analysis, decision, execution, portfolio, rebalance, performance, watchlist, backtest, simulation, monitoring)
- WebSocket `/ws/live` untuk real-time engine status
- Runtime toggle endpoints untuk auto-trade dan rebalance (no restart needed)
- Engine registry dengan 18 engine terdaftar
- Dynamic engine status check via importlib

### Added — Frontend

- Next.js 16 (App Router), React 19, TypeScript, TailwindCSS v4
- Dashboard page: candlestick chart, factor scores bar chart, recommendation panel, XAI explanation, execution log, auto-trade toggle, rebalance panel + toggle, performance analytics, watchlist, system health
- Engine Monitor page: WebSocket real-time, engine status grid, connection status
- Terminal layout theme (zinc-950 dark, monospace font)
- PriceChart component (TradingView Lightweight Charts)
- API proxy via Next.js rewrites

### Added — CLI

- 12 commands: fetch, compute-scores, recommend, explain, backtest, paper-trade, monitor, corporate-actions, relationship, execution, test-e2e, list

### Added — Infrastructure

- Daily runner script (scheduler untuk fetch + compute + notify)
- E2E test script
- Production start scripts (Linux .sh + Windows .bat)
- Dockerfile + docker-compose.yml
- Telegram notifier untuk order execution, risk alerts, anomaly detection
- .env.example dengan semua environment variables

### Added — Testing

- 117 unit tests (10 file test) covering all engines
- 4 E2E browser tests (Playwright): dashboard loads, analyze ticker, change ticker, API proxy reachable
- Demo recording script (Playwright video)

### Added — Documentation

- `docs/buku-sistem-trading.md` — Technical guide lengkap (2400+ baris, 24 bab + 4 lampiran)
- `docs/arsitektur-sistem-trading.md` — Architecture document (layered design, data flow, design patterns)
- `docs/STATUS.md` — Implementation status per modul
- `docs/API_REFERENCE.md` — Detailed API reference dengan contoh request/response
- `README.md` — Project overview, setup, CLI, API, testing, deployment
- `frontend/README.md` — Frontend-specific documentation
- `CHANGELOG.md` — This file

### Dependencies

- Backend: pandas, numpy, yfinance, pyarrow, sqlalchemy, pydantic, fastapi, uvicorn, httpx, feedparser, scikit-learn, python-dateutil, pytest, playwright
- Frontend: next 16.2.12, react 19.2.4, typescript 5.9.7, tailwindcss 4.1.16, lightweight-charts

---

## Versioning

Proyek ini menggunakan Semantic Versioning: `MAJOR.MINOR.PATCH`

- **MAJOR:** Breaking changes (API incompatible, database schema migration required)
- **MINOR:** New features (backward compatible)
- **PATCH:** Bug fixes (backward compatible)

## Release Process

1. Update `CHANGELOG.md` dengan perubahan baru
2. Update version di `config.py` dan `README.md`
3. Run full test suite: `python -m pytest tests/unit/ -v`
4. Run E2E tests: `python -m pytest tests/e2e/ -v`
5. Git commit dengan format: `release: vX.Y.Z — description`
6. Git tag: `git tag v0.Y.Z && git push origin v0.Y.Z`
