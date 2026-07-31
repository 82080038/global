# Status Implementasi Sistem Trading

> **Versi aplikasi:** 0.1.0  
> **Update:** 1 Agustus 2026  
> **Total unit tests:** 553 (semua passing, 0 warnings)

## Perbaikan Terbaru (implementasi `docs/SARAN_PENGEMBANGAN.md`)

**P0 — Bug kritis (selesai):**
- Lexicon sentimen: `"rugi"` dihapus dari `POSITIVE_WORDS`, kata netral/ambigu dibuang, negasi ("tidak untung") kini ditangani (`sentiment/engine.py`).
- Dead code CLI backtest (blok `elif` duplikat) dihapus; `--monte-carlo`/`--walk-forward` kini berjalan (`cli.py`).
- Sinyal SELL berbasis conviction diimplementasikan (`decision/engine.py::decide_action`, ambang `EXIT_CONVICTION_THRESHOLD` di `config.py`).
- AI Learning: koefisien negatif di-clip ke 0 (bukan `np.abs`), validasi out-of-sample via `TimeSeriesSplit`, ambang minimal sampel dinaikkan 20→60 (`ai_learning/engine.py`).

**P1 — Kebenaran kuantitatif & keamanan (selesai):**
- `TRADING_CAPITAL` & `EXIT_CONVICTION_THRESHOLD` disatukan sebagai satu sumber kebenaran di `config.py`, dipakai konsisten di `risk/engine.py`, `decision/engine.py`, `execution/automated.py`, `cli.py`, `api/app.py`.
- Daily loss limit kini dihitung dari kolom `orders.realized_pnl` yang dipersist saat SELL (bukan estimasi rata-rata BUY historis); flag halt dipersist di tabel `system_state` lintas siklus (`execution/automated.py`, `data/storage.py`).
- Keamanan API: `secrets.compare_digest` (anti timing-attack), autentikasi WebSocket `/ws/live` via token, `API_KEY` wajib non-kosong saat `ENV=production` (fail-fast), endpoint sensitif (`/api/execution/toggle`, `/api/rebalance/toggle`) selalu wajib API key, rate-limiter membersihkan entri IP idle (`api/app.py`).
- Historical VaR (percentile empiris) ditambahkan sebagai pembanding VaR parametrik (`risk/engine.py`).

**Sprint 2 — Kebenaran kuantitatif (selesai):**
- Backtest engine: eksekusi next-bar-open (`df["open"].shift(-1)`) untuk eliminasi look-ahead bias; share count dibulatkan ke lot IDX (100); fill price dibulatkan ke tick size IDX (Rp1/2/5/10/25); `run` dan `run_with_data` disatukan ke `_run_core` (§3.1).
- `ConvictionStrategy`: backtest strategi conviction multi-factor yang mereplay skor historis dari tabel `scores` (point-in-time via `merge_asof`) dan menghasilkan sinyal BUY/SELL sesuai `decide_action` (§3.2).
- Block bootstrap Monte Carlo: parameter `block_size` di `monte_carlo_simulation` untuk preserve autokorelasi & volatility clustering (§3.6).
- Refresh data macro/global berbasis umur: `ensure_data` kini cek `max_age_days` (default 1 hari bursa) dan re-fetch jika data basi; `data_age_days` ditambahkan ke breakdown skor (§4.2).
- `IDX_LOT_SIZE` (100) dan `idx_tick_size()` / `round_to_tick()` helper ditambahkan ke `config.py`.

**Sprint 3 — Data archive & modul port (selesai):**
- Export seluruh MySQL `data_pasar_modal` (60+ tabel, 1.5M baris) + `market_master` (5 tabel) + `data_ingestion` (1 tabel) + SQLite `saham.db` (3 tabel) ke Parquet archive di external HDD `K:\trading_data\raw` (total ~33 MB, 170+ files).
- `DATA_ARCHIVE_DIR` config + env var untuk fleksibilitas lokasi archive.
- `ArchiveAdapter` untuk baca/tulis Parquet archive dengan date filtering.
- `scripts/export_mysql_to_parquet.py` — multi-database export dengan year partitioning.
- `scripts/export_sqlite_to_parquet.py` — export SQLite ke Parquet.
- Port modul dari `pasar_modal`:
  - `analysis/regime.py` — market regime detection (trending/neutral/volatile/shock).
  - `risk/kelly.py` — Kelly Criterion position sizing.
  - `execution/tax.py` — Indonesia stock tax calculator (PPh, broker fee, clearing, dividend).
  - `analysis/red_flags.py` — fundamental red flags detection (earnings quality, balance sheet, governance).
  - `analysis/screener.py` — stock screener (technical, momentum, value templates).
  - `data/idx_scraper.py` — IDX.co.id scraper untuk foreign flow data.

**Sprint 4 — TIP Component Adoption (selesai):**
- Layer 1: CC (Data Quality Engine) + DD (Rate Limiter with circuit breaker) — `data/quality.py`, `data/rate_limit.py` ✅
- Layer 2: K (Advanced Technical: Ichimoku, Williams %R, OBV, Stoch RSI) + F (Enhanced Regime) + X (Factor Engine: momentum, low_vol, quality, beta, size, value) — `analysis/advanced_technical.py`, `analysis/enhanced_regime.py`, `analysis/factor_engine.py` ✅
- Layer 3: Y (Alpha Composer) + Z (No-Trade Engine: 9 gates) — `analysis/alpha_composer.py`, `analysis/no_trade.py` ✅
- Layer 4: FF (Enhanced Risk Engine: vol-targeting, sector caps, drawdown/beta guards, stop-loss/trailing) + EE (Alpha Validation Lab: VALID/WATCH/REJECT) — `risk/enhanced_risk.py`, `analysis/alpha_validation.py` ✅
- Layer 5: N (Labeling: forward return, triple barrier, alpha-adjusted) + S (Deep Learning: LSTM/MLP) + T (Ensemble: voting/weighted/stacking) + L (Model Registry: versioned storage) — `ai_learning/labeling.py`, `ai_learning/deep_learning.py`, `ai_learning/ensemble.py`, `ai_learning/model_registry.py` ✅
- Layer 6: C (Purged TSS) + D (Walk-Forward) + V (Trading Expectancy) + H (Performance Attribution) + I (Correlation Sizing) + AA (Cross-Asset) + BB (Lead-Lag) + M (Manipulation Detector) + Q (Factor Screener) — `ai_learning/purged_tss.py`, `ai_learning/walk_forward.py`, `risk/expectancy.py`, `analysis/attribution.py`, `risk/corr_sizing.py`, `analysis/cross_asset.py`, `analysis/lead_lag.py`, `analysis/manipulation.py`, `analysis/factor_screener.py` ✅
- Test plan: `docs/TEST_PLAN.md` ✅
- Blueprint extraction: `docs/TIP_BLUEPRINT_EXTRACTION.md` ✅
- Total TIP component tests: 155 new tests across 6 test files ✅

**Belum dikerjakan:** Seluruh item P3 (lihat `docs/SARAN_PENGEMBANGAN.md`).

**§13.5 #5 — Import Parquet/MySQL → SQLite (selesai):**
- `LegacyDataImporter` di `data/import_legacy.py` — import dari `saham.db` ke global DB
- 47,694 rows imported: OHLCV (23,851), global_market_data (15,046), macro_data (8,776), instruments (21)
- CLI command `import-legacy --source <path>`
- 6 unit tests

**P2-6 — Ruff + mypy + coverage gate di CI (selesai):**
- Ruff: 192 errors → 0 (247 auto-fixed), config di `pyproject.toml`
- mypy: non-blocking mode, `ignore_missing_imports=true`
- Coverage gate: 50% minimum (actual 69%), `--cov-fail-under=50`
- CI workflow updated: pyflakes → ruff + mypy + pytest-cov
- Bug fix: `cli.py` F821 undefined name `engine` (moved before use)

**P2-5 — WS broadcast cache + pagination (selesai):**
- Engine status cache (3s TTL) untuk WS `/ws/live` — tidak recompute setiap 5 detik
- Pagination di `/api/tickers`, `/api/data/ohlcv`, `/api/watchlist/all`
- 7 unit tests

**Komponen U — Order Book Analyzer (selesai):**
- `analysis/order_book.py` — gap detection, support/resistance, market efficiency, gap fill predictions
- Raw copy dari `trading-otomatis-indonesia/python/ai_components/order_book_analyzer.py`
- 17 unit tests

**Komponen P — Email Notification (selesai):**
- `utils/notifier.py` — `send_email()` SMTP dengan starttls, `notify_with_fallback()` Telegram→email
- Extract dari `swing/modules/alert_notifier.py`, adaptasi ke `global` conventions
- 8 unit tests

**Komponen W — World Monitor patterns (selesai):**
- `analysis/world_monitor.py` — 7-signal market composite + CII (Country Instability Index) scoring
- Reverse-engineered dari `worldmonitor` (TypeScript) docs/methodology/cii-risk-scores.mdx
- CII: 4 components (Unrest, Conflict, Security, Information), 20 country weights, boost caps
- 7-signal: convergence, velocity_spike, silent_divergence, sector_cascade, dll.
- 27 unit tests

**P2-2 — DataSourceAdapter multi-sumber + incremental fetch (selesai):**
- `SQLiteAdapter` — import dari legacy SQLite DB (saham.db) dengan column mapping
- `CSVAdapter` — import dari CSV files dengan `kode`/`date` column mapping
- `DataSourceManager` — multi-source routing dengan priority fallback + auto last_timestamp lookup
- `fetch_incremental()` — otomatis query last timestamp dari storage, hanya fetch data baru
- 18 unit tests

**P2-1 — Integrasi corporate action → adjusted_close (selesai):**
- Formula split diperbaiki: `*= 1/ratio` (sebelumnya `*= ratio` — terbalik)
- Formula dividend diperbaiki: `*= (close-d)/close` (sebelumnya `*= close/(close-d)` — terbalik)
- `acquisition.py` auto-fetch corporate actions + `update_adjusted_close` setelah OHLCV save
- Column mapping `Adj Close` → `adjusted_close` (sebelumnya `adj_close` — tidak tersimpan)
- CLI command `update-adjusted-close <ticker>`
- Bug fix: `storage.py::update_adjusted_close` referenced `self.storage` → `self`
- 9 unit tests

**P2-3 — WAL + executemany + Alembic (selesai):**
- WAL journal mode set persistent di `_init_db()` + `synchronous=NORMAL` + 64MB cache
- `executemany_batch()` helper untuk large imports dengan chunking (default 5000 rows/batch)
- 18 tabel D1–D31 ditambahkan ke SCHEMA + Alembic migration `0002_d1_d31_tables.py`
- `_migrate_legacy_tables()` — rename legacy tables dengan schema tidak kompatibel (kode→ticker, tanggal→date, dll)
- 10 unit tests

**P2-4 — Konsolidasi ATR/fee/slippage (selesai):**
- `risk/costs.py` sebagai single source of truth: `compute_atr()`, `get_latest_atr()`, `CostModel` (buy/sell fee, levy, slippage, simulate_fill, check_feasibility)
- `risk/engine.py` — `_atr()` dan slippage kini delegasi ke `costs.py`
- `execution/engine.py` — semua fee/slippage/fill delegasi ke `CostModel`
- `execution/automated.py` — ATR dan fee kini dari `costs.py` (fix broken import)
- `backtest/engine.py` — `CostModel` dihapus, import dari `risk/costs.py`
- `analysis/technical.py` — ATR kini dari `costs.py::compute_atr()`

## Legenda

- ✅ **Done** — Fully implemented and tested
- 🔧 **Partial** — Core logic implemented, some features pending
- 📋 **Planned** — Designed but not yet implemented
- ❌ **Not started** — Not yet implemented

---

## Data Layer

| Modul | File | Status | Catatan |
|-------|------|--------|---------|
| Data Acquisition | `data/acquisition.py` | ✅ Done | Yahoo Finance via yfinance, multi-ticker, auto-retry |
| Data Validation | `data/validation.py` | ✅ Done | Completeness, plausibility, cross-source (adj_close vs close), reconciliation (volume, OHLCV) |
| Data Storage | `data/storage.py` | ✅ Done | SQLite, 13 tabel (+`system_state` untuk flag persisten), raw/clean zone, Parquet export |
| Data Contracts | `data/contracts.py` | ✅ Done | Pydantic models: OHLCVRecord, DataSourceHealth, DataQualityReport |
| Database Seeder | `data/seeder.py` | ✅ Done | Seed data untuk testing |

## Analysis Layer

| Modul | File | Status | Catatan |
|-------|------|--------|---------|
| Technical Analysis | `analysis/technical.py` | ✅ Done | RSI, MACD, MA20/50/200, Bollinger Bands, ADX, OBV |
| Fundamental Analysis | `analysis/fundamental.py` | 🔧 Partial | P/E, P/B, ROE, Debt/Equity, Dividend Yield via yfinance; DCF/Z-Score belum |
| Macro Economic | `analysis/macro.py` | ✅ Done | Proxy via US10Y, GOLD, OIL, USD/IDR, DXY; regime detection |
| Global Market | `analysis/global_market.py` | ✅ Done | Correlation dengan S&P500, Nikkei, CSI300, STOXX600 |
| Market Relationship | `intelligence/relationship.py` | ✅ Done | Rolling correlation, lag analysis, lead/lag matrix |
| Analysis Pipeline | `analysis/pipeline.py` | ✅ Done | Orchestration semua engine, parallel execution |

## Sentiment Layer

| Modul | File | Status | Catatan |
|-------|------|--------|---------|
| NLP News Engine | `sentiment/engine.py` | ✅ Done | RSS Bisnis.com/Kontan/CNBC ID, Indonesian lexicon, fallback proxy |
| Foreign Flow | `sentiment/foreign_flow.py` | ✅ Done | Volume+price proxy untuk foreign accumulation/distribution |
| Broker Summary | `sentiment/broker_summary.py` | ✅ Done | IDX public API + yfinance institutional fallback, smart money classification |
| Social Media | `sentiment/social_media.py` | 🔧 Partial | Reddit + X/Twitter integration; butuh API keys untuk aktif |
| Google Trends | `sentiment/google_trends.py` | 🔧 Partial | pytrends integration; rate-limited, butuh pip install pytrends |

## Risk Layer

| Modul | File | Status | Catatan |
|-------|------|--------|---------|
| Risk Engine | `risk/engine.py` | ✅ Done | ATR-based position sizing, stop-loss, take-profit, VaR, slippage, liquidity check |
| Daily Risk Metrics | `risk/engine.py` | ✅ Done | VaR 95/99, CVaR, max drawdown, annualized volatility — saved to DB |

## Portfolio Layer

| Modul | File | Status | Catatan |
|-------|------|--------|---------|
| Portfolio Engine | `portfolio/engine.py` | ✅ Done | Read positions from DB, generate BUY/SELL orders, exposure tracking |
| Performance Analytics | `portfolio/performance.py` | ✅ Done | Equity curve, Sharpe, drawdown, win rate, profit factor, daily snapshots |
| Portfolio Rebalancer | `portfolio/rebalancer.py` | ✅ Done | Target weights, drift detection, auto/manual rebalance, runtime toggle |

## Execution Layer

| Modul | File | Status | Catatan |
|-------|------|--------|---------|
| Execution Engine | `execution/engine.py` | ✅ Done | Fee calculation (broker, levy, PPh), slippage, simulate fill, feasibility check |
| Automated Execution | `execution/automated.py` | ✅ Done | Robot trader, signal processing, stop-loss/take-profit/trailing monitor, daily loss limit |

## Intelligence Layer

| Modul | File | Status | Catatan |
|-------|------|--------|---------|
| Decision Engine | `decision/engine.py` | ✅ Done | Weighted scoring, BUY/HOLD/WATCHLIST/AVOID, conviction score |
| XAI Engine | `xai/engine.py` | ✅ Done | Narrative explanation, top factors, confidence interval |
| AI Learning Engine | `ai_learning/engine.py` | ✅ Done | Regime weights, consistency adjustment, Linear Regression training |

## Simulation & Testing

| Modul | File | Status | Catatan |
|-------|------|--------|---------|
| Paper Trading | `paper_trading/engine.py` | ✅ Done | Simulate order dengan harga pasar, PnL tracking |
| Backtest Engine | `backtest/engine.py` | ✅ Done | Buy & hold, MA crossover, cost model |
| Backtest Metrics | `backtest/metrics.py` | ✅ Done | Monte Carlo simulation, Walk-Forward analysis |
| Backtest Strategies | `backtest/strategies.py` | ✅ Done | Strategy implementations |
| Monitoring Engine | `monitoring/engine.py` | ✅ Done | System health, source status, alert detection |

## Corporate Actions

| Modul | File | Status | Catatan |
|-------|------|--------|---------|
| Corporate Actions | `corporate/actions.py` | ✅ Done | Split & dividend detection, price adjustment, adj_factor |

## API Layer

| Modul | File | Status | Catatan |
|-------|------|--------|---------|
| FastAPI App | `api/app.py` | ✅ Done | 30+ REST endpoints, WebSocket, runtime toggles, engine registry |

## Frontend

| Modul | File | Status | Catatan |
|-------|------|--------|---------|
| Dashboard | `app/dashboard/page.tsx` | ✅ Done | Charts, scores, recommendation, execution log, toggles, performance, watchlist |
| Engine Monitor | `app/engines/page.tsx` | ✅ Done | WebSocket real-time, engine status grid |
| Terminal Layout | `components/TerminalLayout.tsx` | ✅ Done | Header, sidebar, navigation |
| Price Chart | `components/PriceChart.tsx` | ✅ Done | Candlestick via TradingView Lightweight Charts |

## CLI

| Command | Status | Catatan |
|---------|--------|---------|
| `fetch` | ✅ Done | Multi-ticker, period option |
| `compute-scores` | ✅ Done | All engines |
| `recommend` | ✅ Done | BUY/HOLD/WATCHLIST/AVOID |
| `explain` | ✅ Done | XAI narrative |
| `backtest` | ✅ Done | + Monte Carlo + Walk-Forward |
| `paper-trade` | ✅ Done | Simulation |
| `monitor` | ✅ Done | Health check |
| `corporate-actions` | ✅ Done | Split/dividend |
| `relationship` | ✅ Done | Rolling correlation |
| `execution` | ✅ Done | Robot trader, --once / --interval |
| `test-e2e` | ✅ Done | End-to-end pipeline test |
| `list` | ✅ Done | Tickers in DB |

## Infrastructure

| Modul | File | Status | Catatan |
|-------|------|--------|---------|
| Structured Logging | `utils/logging_config.py` | ✅ Done | dictConfig with rotation (10MB file, 5MB error file), env-configurable level |
| Daily Runner | `scripts/daily_runner.py` | ✅ Done | 7-step pipeline: fetch → scores → recommendations → execution → risk → performance → notify |
| E2E Test Script | `scripts/test_end_to_end.py` | ✅ Done | Full pipeline test |
| Start Production (Linux) | `scripts/start_production.sh` | ✅ Done | Backend + frontend |
| Start Production (Windows) | `scripts/start_production.bat` | ✅ Done | Backend + frontend |
| Dockerfile | `Dockerfile` | ✅ Done | Backend container |
| docker-compose.yml | `docker-compose.yml` | ✅ Done | Multi-service |
| Telegram Notifier | `utils/notifier.py` | ✅ Done | Alert untuk order, risk, anomaly |
| Database Migration | `alembic/` | ✅ Done | Alembic setup with initial schema migration, SQLite batch mode |

## Testing

| Layer | Status | Jumlah |
|-------|--------|--------|
| Unit Tests | ✅ Done | 553 tests (26 file) — includes 155 TIP + 20 CRUD + 16 API tests |
| E2E Tests | ✅ Done | 4 browser tests (Playwright) |
| Lint | ✅ Done | ruff clean, mypy non-blocking |

## Roadmap (Belum Implemented)

| Fitur | Prioritas | Catatan |
|-------|-----------|---------|
| DCF Valuation | Medium | Fundamental analysis enhancement |
| Altman Z-Score | Medium | Fundamental analysis enhancement |
| Piotroski F-Score | Medium | Fundamental analysis enhancement |
| Ichimoku / Stochastic | ✅ Done | `analysis/advanced_technical.py` — Ichimoku, Williams %R, OBV, Stoch RSI |
| Markowitz Optimization | Medium | Portfolio mean-variance optimization |
| Walk-Forward CV | ✅ Done | `ai_learning/walk_forward.py` + `ai_learning/purged_tss.py` |
| Bayesian Updating | Low | AI Learning real-time adaptation |
| Mobile Responsive | Low | Frontend |
| Dark/Light Toggle | Low | Frontend |

---

## Architecture Summary

```
Data Layer → Analysis Layer → Sentiment Layer → Risk Layer
                ↓                                       ↓
         Intelligence Layer ← ← ← ← ← ← ← ← ← ← ← ← ←
                ↓
         Decision Engine → XAI Engine → AI Learning Engine
                ↓
         Portfolio Engine → Execution Engine → Automated Execution
                ↓
         Monitoring Engine → Telegram Notifier
```

**Total engines:** 18 base + 18 TIP-adopted = 36 (lihat Lampiran C di buku-sistem-trading.md)  
**Total API endpoints:** 59 REST (47 GET/POST + 12 DELETE) + 1 WebSocket  
**Total database tables:** 13  
**Total unit tests:** 553
