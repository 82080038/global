# Status Implementasi Sistem Trading

> **Versi aplikasi:** 0.1.0  
> **Update:** 31 Juli 2026  
> **Total unit tests:** 182 (semua passing)

## Perbaikan Terbaru (implementasi `docs/SARAN_PENGEMBANGAN.md`)

**P0 — Bug kritis (selesai):**
- Lexicon sentimen: `"rugi"` dihapus dari `POSITIVE_WORDS`, kata netral/ambigu dibuang, negasi ("tidak untung") kini ditangani (`sentiment/engine.py`).
- Dead code CLI backtest (blok `elif` duplikat) dihapus; `--monte-carlo`/`--walk-forward` kini berjalan (`cli.py`).
- Sinyal SELL berbasis conviction diimplementasikan (`decision/engine.py::decide_action`, ambang `EXIT_CONVICTION_THRESHOLD` di `config.py`).
- AI Learning: koefisien negatif di-clip ke 0 (bukan `np.abs`), validasi out-of-sample via `TimeSeriesSplit`, ambang minimal sampel dinaikkan 20→60 (`ai_learning/engine.py`).

**P1 — Kebenaran kuantitatif & keamanan (selesai sebagian):**
- `TRADING_CAPITAL` & `EXIT_CONVICTION_THRESHOLD` disatukan sebagai satu sumber kebenaran di `config.py`, dipakai konsisten di `risk/engine.py`, `decision/engine.py`, `execution/automated.py`, `cli.py`, `api/app.py`.
- Daily loss limit kini dihitung dari kolom `orders.realized_pnl` yang dipersist saat SELL (bukan estimasi rata-rata BUY historis); flag halt dipersist di tabel `system_state` lintas siklus (`execution/automated.py`, `data/storage.py`).
- Keamanan API: `secrets.compare_digest` (anti timing-attack), autentikasi WebSocket `/ws/live` via token, `API_KEY` wajib non-kosong saat `ENV=production` (fail-fast), endpoint sensitif (`/api/execution/toggle`, `/api/rebalance/toggle`) selalu wajib API key, rate-limiter membersihkan entri IP idle (`api/app.py`).
- Historical VaR (percentile empiris) ditambahkan sebagai pembanding VaR parametrik (`risk/engine.py`).

**Belum dikerjakan (lihat `docs/SARAN_PENGEMBANGAN.md` untuk detail):** look-ahead bias backtest (§3.1), `ConvictionStrategy` backtest (§3.2), block-bootstrap Monte Carlo, refresh data macro/global berbasis umur, konsolidasi ATR/fee, `DataSourceAdapter` multi-sumber, dan seluruh item P3.

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
| Unit Tests | ✅ Done | 154 tests (18 file) |
| E2E Tests | ✅ Done | 4 browser tests (Playwright) |
| Lint | ✅ Done | pyflakes clean |

## Roadmap (Belum Implemented)

| Fitur | Prioritas | Catatan |
|-------|-----------|---------|
| DCF Valuation | Medium | Fundamental analysis enhancement |
| Altman Z-Score | Medium | Fundamental analysis enhancement |
| Piotroski F-Score | Medium | Fundamental analysis enhancement |
| Ichimoku / Stochastic | Low | Additional technical indicators |
| Markowitz Optimization | Medium | Portfolio mean-variance optimization |
| Walk-Forward CV | Medium | AI Learning cross-validation |
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

**Total engines:** 18 (lihat Lampiran C di buku-sistem-trading.md)  
**Total API endpoints:** 30+ REST + 1 WebSocket  
**Total database tables:** 13  
**Total unit tests:** 182
