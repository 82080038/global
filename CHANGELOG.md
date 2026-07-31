# Changelog

Semua perubahan penting pada proyek ini didokumentasikan dalam file ini.

Format berdasarkan [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), dan proyek ini mengikuti [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.7] — 2026-08-01

Complete CRUD operations, frontend-backend integration fixes, lint cleanup, security hardening.

### Added — CRUD Operations

- **12 Delete methods** in `DataStorage`: `delete_ohlcv`, `delete_scores`, `delete_orders`, `delete_audit_logs`, `delete_position`, `delete_ai_weights`, `delete_equity_snapshots`, `delete_daily_risk_metrics`, `delete_relationships`, `delete_corporate_actions`, `delete_news`.
- **`get_audit_logs`** Read method with filtering + pagination in `DataStorage`.
- **`get_open_position_by_id`** Read method in `DataStorage`.
- **`update_watchlist`** Update method in `DataStorage`.
- **`delete_archived_ticker`** in `ArchiveAdapter` for Parquet file deletion.
- **12 DELETE API endpoints** for all resources + **GET `/api/audit`** for audit log reading.
- **GET `/api/portfolio/exposure`** endpoint for portfolio exposure summary.
- **PATCH `/api/positions/{position_id}`** endpoint for updating position fields (stop_loss, take_profit, status, etc.).
- **PUT `/api/watchlist/{ticker}`** endpoint for updating watchlist notes/favorite status.
- **PUT `/api/system-state/{key}`** + **GET `/api/system-state/{key}`** endpoints for circuit breaker flags and runtime state.
- Total API routes: **63 REST** (47 GET/POST + 12 DELETE + 4 PATCH/PUT/GET update) + 1 WebSocket.

### Fixed — Security Hardening

- **DELETE method protection**: All DELETE requests now require API key (previously only 2 toggle endpoints were sensitive).
- **Destructive POST endpoints** (`/api/execution/run`, `/api/rebalance`, `/api/fetch`) added to `_SENSITIVE_PATHS`.
- **API version** updated from `0.1.0` to `0.1.7` in FastAPI app metadata.

### Fixed — Frontend-Backend Integration

- **Audit page** (`audit/page.tsx`): Fixed field mapping mismatch — was reading `data.entries` with `id/action/detail` fields; now correctly reads `data.logs` with `event_id/event_type/payload/timestamp/actor`.
- **Backtest page** (`backtest/page.tsx`): Changed from GET to POST — API endpoint is `POST /api/backtest`, not `GET /api/backtest/{ticker}`.
- **Dashboard page** (`dashboard/page.tsx`): Fixed all fetch calls to use `API_BASE` consistently (was mixing relative `/api/...` paths with absolute URLs).

### Fixed — Lint & Code Quality

- **108 ruff lint errors** fixed in test files (unused imports, unsorted imports, f-string placeholders, UP017 datetime.UTC alias, SIM300 Yoda conditions).
- All test files now pass `ruff check` with zero errors.

### Fixed — Documentation

- **STATUS.md**: Database table count corrected from 13 to 32 (actual count).
- **API_REFERENCE.md**: Added `GET /api/portfolio/exposure` documentation.
- **CHANGELOG.md**: Fixed version numbering (0.1.6 → 0.1.5, was duplicate).

### Fixed — CI

- **CI workflow**: Added `tests/unit/` to ruff check (was only checking `src/`).
- **CI workflow**: Added `npm run lint` step before frontend build.

### Cleanup

- Removed duplicate script `scripts/import_archive_to_sqlite.py` (superseded by `import_legacy_data.py`).
- Updated `.gitignore`: added `.mypy_cache/`, `.ruff_cache/`, `data/archive/*.parquet`.
- Added `.gitkeep` to `data/` and `data/archive/` (folders were empty in repo).

### Tests

- Total: **562 unit tests** (was 537), all passing, 0 warnings.
- Added 25 API endpoint tests (2 audit, 2 portfolio exposure, 12 DELETE, 9 PATCH/PUT/GET update).
- Ruff clean on both `src/` and `tests/`.
- Frontend ESLint clean (0 warnings).

---

## [0.1.5] — 2026-08-01

Data archive & port modul dari proyek `pasar_modal`.

### Added — Data Archive

- **`DATA_ARCHIVE_DIR`** config + env var untuk fleksibilitas lokasi archive (`config.py`).
- **`ArchiveAdapter`** — baca/tulis Parquet archive dengan date filtering, list tickers, archive info (`data/archive.py`).
- **`scripts/export_mysql_to_parquet.py`** — multi-database export (data_pasar_modal + market_master + data_ingestion) dengan year partitioning untuk tabel besar.
- **`scripts/export_sqlite_to_parquet.py`** — export SQLite `saham.db` ke Parquet.
- Export lengkap: 1.5M+ baris MySQL + 47K baris SQLite → ~33 MB Parquet di external HDD `K:\trading_data\raw`.

### Added — Ported Modules

- **`analysis/regime.py`** — market regime detection (trending/neutral/volatile/shock) berbasis VIX, IHSG vs SMA200, korelasi.
- **`risk/kelly.py`** — Kelly Criterion position sizing dengan half/quarter Kelly, confidence interval, dan kalkulasi dari trade history.
- **`execution/tax.py`** — Indonesia stock tax calculator (PPh final 0.1%, broker fee, clearing fee, custody fee, dividend tax 10%).
- **`analysis/red_flags.py`** — fundamental red flags detection: earnings quality (cash conversion, accruals, DSO, inventory turnover), balance sheet health (current ratio, D/E, goodwill, short-term debt), governance (auditor changes, related-party, pledging, independent directors).
- **`analysis/screener.py`** — stock screener dengan template technical, momentum, dan value.
- **`data/idx_scraper.py`** — IDX.co.id scraper untuk foreign flow data per stock.

### Tests

- 37 new tests untuk ported modules (regime, kelly, tax, red_flags, screener).
- 5 tests untuk ArchiveAdapter.
- Total: 235 tests, semua passing.

---

## [0.1.4] — 2026-07-31

Implementasi Sprint 2 dari `docs/SARAN_PENGEMBANGAN.md` — kebenaran kuantitatif.

### Fixed (§3.1 — look-ahead bias backtest)

- **Next-bar-open execution**: sinyal di bar t dieksekusi di open bar t+1 (`df["open"].shift(-1)`), bukan close bar yang sama — menghapus look-ahead bias 1 bar — `backtest/engine.py`.
- **Lot IDX (100)**: share count dibulatkan ke kelipatan `IDX_LOT_SIZE` (100 lembar), konsisten dengan `execution/automated.py` — `backtest/engine.py`, `config.py`.
- **Tick size IDX**: fill price dibulatkan ke tick size BEI (Rp1 <200, Rp2 <500, Rp5 <2000, Rp10 <5000, Rp25 ≥5000) via `round_to_tick()` — `config.py`, `backtest/engine.py`.
- **Refactor**: `run` dan `run_with_data` disatukan ke `_run_core` (sebelumnya ~90% duplikat) — `backtest/engine.py`.

### Added (§3.2 — ConvictionStrategy backtest)

- `ConvictionStrategy` di `backtest/strategies.py`: strategi backtest yang mereplay skor historis dari tabel `scores` (point-in-time via `pd.merge_asof` direction="backward") dan menghasilkan sinyal BUY/SELL sesuai logika `decide_action` (conviction ≥ 70 → BUY, < EXIT_CONVICTION_THRESHOLD → SELL). CLI: `--strategy conviction`.

### Added (§3.6 — Block bootstrap Monte Carlo)

- Parameter `block_size` di `monte_carlo_simulation` — block bootstrap yang preserve autokorelasi & volatility clustering (sebelumnya IID bootstrap saja). CLI: `--block-size N`. API: field `block_size` di `/api/backtest/monte-carlo`.

### Fixed (§4.2 — Refresh data macro/global berbasis umur)

- `MacroEconomicEngine.ensure_data` dan `GlobalMarketEngine.ensure_data` kini menerima `max_age_days` (default 1); re-fetch jika `max(timestamp)` lebih tua dari threshold — sebelumnya data hanya di-fetch jika tabel kosong (sekali fetch, selamanya basi).
- `data_age_days` ditambahkan ke breakdown skor macro & global agar Decision Engine dapat mendiskon faktor basi — `analysis/macro.py`, `analysis/global_market.py`.

### Added

- Konstanta `IDX_LOT_SIZE` (100) dan helper `idx_tick_size()` / `round_to_tick()` di `config.py`.
- 16 unit test baru (total 182 → 198): `TestIDXTickSize`, `TestNextBarOpenExecution`, `TestConvictionStrategy`, `TestBlockBootstrapMC` di `test_backtest.py`.

---

## [0.1.3] — 2026-07-31

Implementasi temuan P0/P1 dari `docs/SARAN_PENGEMBANGAN.md`.

### Fixed (P0 — bug kritis)

- **Sentiment lexicon**: `"rugi"` dihapus dari `POSITIVE_WORDS` (sebelumnya ada di kedua daftar sehingga saling menetralkan skor), kata netral/ambigu (`volume`, `transaksi`, `target`, `konsolidasi`) dibuang, ditambah penanganan negasi ("tidak untung") — `sentiment/engine.py`.
- **CLI dead code**: blok `elif args.cmd == "backtest"` duplikat dihapus; `--monte-carlo`/`--walk-forward` sekarang benar-benar berjalan — `cli.py`.
- **Sinyal SELL**: `DecisionEngine.decide_action` kini mengembalikan `SELL` saat ada posisi terbuka dan konviksi turun di bawah `EXIT_CONVICTION_THRESHOLD` — sebelumnya satu-satunya exit adalah SL/TP/trailing-stop — `decision/engine.py`.
- **AI Learning**: koefisien regresi negatif di-clip ke 0 (bukan `np.abs()`, yang membuang arah/tanda), ditambah validasi out-of-sample `TimeSeriesSplit`, ambang minimal sampel dinaikkan dari 20 ke 60 — `ai_learning/engine.py`.

### Fixed (P1 — kebenaran kuantitatif & keamanan)

- **Modal terpusat**: `TRADING_CAPITAL` dan `EXIT_CONVICTION_THRESHOLD` disatukan di `config.py`, dipakai konsisten di `risk/engine.py`, `decision/engine.py`, `execution/automated.py`, `cli.py`, `api/app.py` (sebelumnya `DecisionEngine.recommend` memanggil risk analyze tanpa capital sehingga posisi dihitung dengan modal 1 miliar meski robot beroperasi dengan `TRADING_CAPITAL`).
- **Daily loss limit**: dihitung dari kolom baru `orders.realized_pnl` yang dipersist saat SELL dieksekusi, bukan estimasi dari rata-rata semua harga BUY historis; flag halt-for-today dipersist di tabel baru `system_state` agar tetap berlaku lintas siklus scheduler — `execution/automated.py`, `data/storage.py`.
- **Keamanan API**: `secrets.compare_digest` untuk perbandingan API key (anti timing-attack), autentikasi token pada handshake WebSocket `/ws/live`, `API_KEY` wajib non-kosong saat `ENV=production` (fail-fast di startup), endpoint sensitif (`/api/execution/toggle`, `/api/rebalance/toggle`) selalu wajib API key meski di dev, rate-limiter membersihkan entri IP idle secara berkala — `api/app.py`.
- **Historical VaR**: ditambahkan sebagai pembanding VaR parametrik yang mengasumsikan distribusi normal (underestimate untuk return fat-tailed IDX) — `risk/engine.py`.

### Added

- Index `orders(created_at)` dan `audit_log(timestamp)`.
- Tabel `system_state` (key-value) untuk flag persisten lintas proses/siklus.
- 65 unit test baru (total 117 → 182): `test_cli.py`, `test_automated_execution.py`, `test_storage.py`, plus regresi tambahan di `test_sentiment.py`, `test_decision.py`, `test_ai_learning.py`, `test_api.py`.

---

## [0.1.2] — 2026-07-31

### Fixed — Remaining Gaps

- Broker Summary: implementasi IDX public API endpoint dengan date parameter + yfinance institutional holders fallback
- Sentiment sub-sources: save aggregate + per-sub-source scores ke DB (sentiment_foreign_flow, sentiment_broker_summary, etc.)
- Data Validation: implementasi cross-source check (adjusted_close vs close ratio) dan reconciliation (volume consistency, OHLCV internal consistency)

### Added — Infrastructure

- Structured logging: `utils/logging_config.py` dengan dictConfig, RotatingFileHandler (10MB main + 5MB error), env-configurable level
- Database migration: Alembic setup (`alembic.ini`, `alembic/env.py`, initial migration) dengan SQLite batch mode support
- Frontend: 3 halaman baru — Backtest (`/backtest`), Portfolio (`/portfolio`), Audit Log (`/audit`)
- TerminalLayout: tambah nav links untuk Backtest, Portfolio, Audit Log
- `alembic` ditambahkan ke requirements.txt

### Changed

- `daily_runner.py`: ganti `basicConfig` ke `setup_logging()` dari logging_config.py
- `app.py`: tambah `setup_logging()` di entry point

---

## [0.1.1] — 2026-07-31

### Fixed — Integration & Sync

- ENGINE_REGISTRY: tambah 3 engine missing (automated_execution, rebalancer, performance_analytics) — sekarang 18 engine
- WebSocket path: `/ws/engines` → `/ws/live` di backend & frontend (sinkron dengan docs)
- Portfolio Engine: baca dari tabel `positions` (sebelumnya hardcoded CASH), handle BUY & SELL, tambah `get_exposure()`
- Daily Runner: tambah 3 step baru — automated execution, daily risk metrics, performance snapshot (7-step pipeline)

### Added — Security & Infrastructure

- CORS middleware (configurable via `CORS_ORIGINS` env var)
- API key authentication (optional, via `API_KEY` env var, header `X-API-Key`)
- Rate limiting (in-memory, per-IP, configurable via `RATE_LIMIT_MAX`)
- Dockerfile HEALTHCHECK
- CI/CD pipeline: `.github/workflows/ci.yml` — lint, test with coverage, frontend build, Docker build
- pytest-cov + `.coveragerc` untuk coverage measurement

### Added — Testing

- 37 unit test baru (117 → 154 total): test_portfolio, test_api, test_sentiment, test_corporate, test_xai, test_monitoring, test_paper_trading, test_notifier

### Removed

- `plotly` dari requirements.txt (tidak digunakan)

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
