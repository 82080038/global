# Developer Guide — Sistem Trading Profesional

> **Dokumen ini adalah panduan utama untuk memahami, menggunakan, dan mengembangkan aplikasi.**
> Baca dokumen ini terlebih dahulu sebelum mulai coding atau menjalankan aplikasi.

---

## Daftar Isi

1. [Apa Itu Aplikasi Ini?](#1-apa-itu-aplikasi-ini)
2. [Quick Start (5 Menit)](#2-quick-start-5-menit)
3. [Arsitektur Sistem](#3-arsitektur-sistem)
4. [Struktur Folder Lengkap](#4-struktur-folder-lengkap)
5. [Backend — Cara Kerja Engine](#5-backend--cara-kerja-engine)
6. [Frontend — Halaman & Komponen](#6-frontend--halaman--komponen)
7. [Database — Skema & Tabel](#7-database--skema--tabel)
8. [API — Endpoint Reference Cepat](#8-api--endpoint-reference-cepat)
9. [CLI — Command Line Interface](#9-cli--command-line-interface)
10. [Konfigurasi & Environment](#10-konfigurasi--environment)
11. [Testing](#11-testing)
12. [Deployment](#12-deployment)
13. [Panduan Pengembangan](#13-panduan-pengembangan)
14. [Dokumentasi Tambahan](#14-dokumentasi-tambahan)

---

## 1. Apa Itu Aplikasi Ini?

Sistem trading otomatis untuk **saham Indonesia (IDX/Bursa Efek Indonesia)** yang menggabungkan:

- **Multi-Factor Analysis** — 7 engine analisis (teknikal, fundamental, makro, global, sentimen, corporate actions, market relationship)
- **Risk Management** — VaR, CVaR, position sizing, daily loss limit, circuit breaker
- **Automated Execution** — Robot trader dengan stop-loss, take-profit, trailing stop
- **Explainable AI** — Rekomendasi BUY/HOLD/SELL dengan narasi penjelasan
- **AI Learning** — Optimasi bobot faktor via Linear Regression dari historikal data
- **Backtesting** — Buy & Hold, MA Crossover, Monte Carlo, Walk-Forward Analysis
- **Frontend Dashboard** — UI terminal-style dengan chart, skor, rekomendasi, execution log
- **Portfolio Rebalancer** — Target weights dengan drift detection

**Target pengguna:** Trader individu Indonesia yang ingin otomatisasi analisis dan eksekusi saham IDX.

---

## 2. Quick Start (5 Menit)

### Prasyarat

- Python 3.11+ (tested on 3.12)
- Node.js 20+ (untuk frontend)
- pip, npm

### Install & Run

```bash
# 1. Clone repo
git clone https://github.com/82080038/global.git
cd global

# 2. Setup Python backend
python -m venv .venv
# Windows:
.\.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate
pip install -r requirements.txt

# 3. Setup environment
cp .env.example .env
# Edit .env — minimal: set API_KEY untuk security

# 4. Fetch data pertama (butuh internet — ambil dari Yahoo Finance)
python -m trading_system.cli fetch BBCA.JK TLKM.JK --period 2y

# 5. Compute scores
python -m trading_system.cli compute-scores BBCA.JK

# 6. Start API server
uvicorn src.trading_system.api.app:app --host 0.0.0.0 --port 8000

# 7. (Terminal terpisah) Start frontend
cd frontend
npm install
npm run dev
```

Buka browser:
- **Frontend:** http://localhost:3000
- **API docs (Swagger):** http://localhost:8000/docs
- **API health:** http://localhost:8000/api/health

---

## 3. Arsitektur Sistem

```
Data Layer                Analysis Layer              Decision Layer
┌─────────────┐          ┌──────────────────┐       ┌──────────────────┐
│ Acquisition │──────→   │ Technical        │──┐    │ Decision Engine  │
│ (YahooFin)  │          │ Fundamental      │  │    │ (weighted score) │
│ Validation  │          │ Macro            │  │    └────────┬─────────┘
│ Storage     │          │ Global Market    │  │             │
│ (SQLite)    │          │ Sentiment (NLP)  │──┤    ┌────────▼─────────┐
│ Archive     │          │ Corporate Actions│  │    │ XAI Engine       │
│ (Parquet)   │          │ Market Relation  │  │    │ (narrative)      │
└─────────────┘          └──────────────────┘  │    └────────┬─────────┘
                                               │             │
┌─────────────┐          ┌──────────────────┐  │    ┌────────▼─────────┐
│ Risk Engine │←─────────│ AI Learning      │←─┘    │ Execution Engine │
│ (VaR, sizing)│         │ (weight optim)   │       │ (automated trade)│
└──────┬──────┘          └──────────────────┘       └────────┬─────────┘
       │                                                     │
       │              ┌──────────────────┐                   │
       └─────────────→│ Portfolio Engine │←──────────────────┘
                      │ (rebalancer)     │
                      └────────┬─────────┘
                               │
                      ┌────────▼─────────┐
                      │ Monitoring Engine│
                      │ + Telegram Alert │
                      └──────────────────┘
```

**Alur data:**
1. **Fetch** data OHLCV dari Yahoo Finance → validasi → simpan ke SQLite
2. **Compute scores** — 7 engine analisis menghasilkan skor 0-100 per ticker
3. **Decision Engine** — gabungkan semua skor dengan bobot → conviction score → BUY/HOLD/SELL
4. **XAI Engine** — generate narasi penjelasan (untuk transparansi)
5. **Risk Engine** — hitung position sizing berdasarkan stop-loss distance
6. **Execution Engine** — jika auto-trade ON, eksekusi order via broker API
7. **Monitoring** — health check + Telegram notification

---

## 4. Struktur Folder Lengkap

```
global/
├── src/trading_system/          # BACKEND (Python)
│   ├── data/                    # Data layer
│   │   ├── acquisition.py       #   Yahoo Finance adapter
│   │   ├── validation.py        #   Data quality validator (tier A/B/C)
│   │   ├── storage.py           #   SQLite storage (32 tables, full CRUD)
│   │   ├── archive.py           #   Parquet archive adapter
│   │   ├── import_legacy.py     #   Import dari legacy DB
│   │   ├── seeder.py            #   Database seeder
│   │   └── contracts.py         #   Data contracts
│   ├── analysis/                # Analysis engines
│   │   ├── technical.py         #   RSI, MACD, MA, Bollinger Bands
│   │   ├── fundamental.py       #   P/E, P/B, ROE, debt ratio
│   │   ├── macro.py             #   Interest rate, inflation, GDP
│   │   ├── global_market.py     #   S&P500, Nikkei, Hang Seng correlation
│   │   ├── pipeline.py          #   Orchestrator untuk semua analysis
│   │   ├── regime.py            #   Market regime detection
│   │   ├── red_flags.py         #   Fundamental red flags
│   │   ├── screener.py          #   Stock screener
│   │   └── technical_indicators.py
│   ├── sentiment/               # Sentiment analysis
│   │   ├── engine.py            #   NLP engine (Indonesian news)
│   │   ├── foreign_flow.py      #   Foreign net buy/sell
│   │   ├── broker_summary.py    #   Broker summary (smart money)
│   │   ├── social_media.py      #   Reddit + X/Twitter
│   │   └── google_trends.py     #   Search trend analysis
│   ├── intelligence/            # Cross-asset intelligence
│   │   └── relationship.py      #   Rolling correlation, lag analysis
│   ├── corporate/               # Corporate actions
│   │   └── actions.py           #   Split, dividend, adjustment factor
│   ├── backtest/                # Backtesting
│   │   ├── engine.py            #   Backtest engine (next-bar-open execution)
│   │   ├── strategies.py        #   BuyAndHold, MA Crossover, Conviction
│   │   └── metrics.py           #   Monte Carlo, Walk-Forward
│   ├── risk/                    # Risk management
│   │   ├── engine.py            #   VaR, CVaR, position sizing
│   │   └── kelly.py             #   Kelly Criterion sizing
│   ├── portfolio/               # Portfolio management
│   │   ├── engine.py            #   Portfolio state
│   │   ├── performance.py       #   Equity curve, Sharpe, drawdown
│   │   └── rebalancer.py        #   Target weights + drift detection
│   ├── execution/               # Order execution
│   │   ├── automated.py         #   Robot trader (auto-trade)
│   │   ├── manual.py            #   Manual order
│   │   └── tax.py               #   Indonesia tax calculator
│   ├── decision/                # Decision engine
│   │   └── engine.py            #   Multi-factor weighted scoring
│   ├── ai_learning/             # AI weight optimization
│   │   └── engine.py            #   Linear Regression on score-return pairs
│   ├── xai/                     # Explainable AI
│   │   └── engine.py            #   Narrative explanation
│   ├── monitoring/              # System monitoring
│   │   └── engine.py            #   Health check + alerts
│   ├── paper_trading/           # Paper trading simulator
│   │   └── engine.py
│   ├── api/                     # REST API
│   │   └── app.py               #   FastAPI app (63 endpoints + 1 WS)
│   ├── utils/                   # Utilities
│   │   ├── notifier.py          #   Telegram notifier
│   │   └── logging_config.py    #   Logging setup
│   ├── cli.py                   # CLI entry point
│   └── config.py                # Global config (capital, fees, tick size)
│
├── frontend/                    # FRONTEND (Next.js + React + Tailwind)
│   ├── app/
│   │   ├── page.tsx             #   Landing page → redirect ke /dashboard
│   │   ├── dashboard/page.tsx   #   Main dashboard (chart, scores, rec, logs)
│   │   ├── audit/page.tsx       #   Audit log viewer
│   │   ├── backtest/page.tsx    #   Backtest runner + results
│   │   ├── portfolio/page.tsx   #   Portfolio positions + exposure
│   │   ├── engines/page.tsx     #   Engine registry (18 engines)
│   │   ├── components/
│   │   │   ├── TerminalLayout.tsx  # Shared layout (sidebar nav)
│   │   │   └── PriceChart.tsx      # Candlestick chart (lightweight-charts)
│   │   ├── layout.tsx           #   Root layout (fonts, metadata)
│   │   └── globals.css          #   Tailwind global styles
│   ├── package.json             #   Next.js 16, React 19, Recharts, Tailwind 4
│   ├── Dockerfile               #   Frontend Docker image
│   └── .env.local               #   NEXT_PUBLIC_API_BASE=http://localhost:8000
│
├── tests/                       # TEST SUITE
│   ├── unit/                    #   562 unit tests (pytest)
│   │   ├── test_api.py          #   39 API endpoint tests
│   │   ├── test_crud_operations.py  # CRUD delete tests
│   │   ├── conftest.py          #   Shared fixtures
│   │   └── ...                  #   Engine-specific tests
│   └── e2e/                     #   Playwright E2E tests
│       ├── test_dashboard.py    #   Dashboard UI tests
│       └── record_demo.py       #   Demo recorder
│
├── scripts/                     # UTILITY SCRIPTS
│   ├── daily_runner.py          #   Cron-style daily job (fetch + compute + trade)
│   ├── import_legacy_data.py    #   Import dari legacy SQLite DB
│   ├── export_mysql_to_parquet.py  # Export MySQL → Parquet
│   ├── export_sqlite_to_parquet.py # Export SQLite → Parquet
│   ├── test_end_to_end.py       #   E2E pipeline test
│   ├── start_production.sh      #   Linux startup script
│   └── start_production.bat     #   Windows startup script
│
├── data/                        # DATA (gitignored, kecuali .gitkeep)
│   ├── trading_system.db        #   SQLite database (32 tables)
│   ├── raw/                     #   Raw data zone
│   ├── clean/                   #   Clean data zone
│   └── archive/                 #   Parquet archive (permanent storage)
│
├── alembic/                     # DATABASE MIGRATIONS
│   └── versions/
│       └── 0001_initial.py      #   Initial schema
│
├── docs/                        # DOCUMENTATION
│   ├── DEVELOPER_GUIDE.md       #   ← YOU ARE HERE
│   ├── API_REFERENCE.md         #   Detailed API docs (all 63 endpoints)
│   ├── STATUS.md                #   Current project status
│   ├── SARAN_PENGEMBANGAN.md    #   Development roadmap (1197 lines)
│   ├── TEST_PLAN.md             #   Test strategy
│   ├── ANALISIS_SUMBER_DATA.md  #   Data source analysis
│   ├── MAPPING_PARQUET_SQLITE.md #  Parquet → SQLite column mapping
│   ├── TIP_BLUEPRINT_EXTRACTION.md # TIP blueprint
│   ├── arsitektur-sistem-trading.md # Architecture deep-dive (58K)
│   └── buku-sistem-trading.md   #   Trading system book (86K)
│
├── .github/workflows/ci.yml     # CI: ruff + mypy + pytest + frontend lint + build + Docker
├── .env.example                 # Environment template (copy to .env)
├── .gitignore                   # Git ignore rules
├── CHANGELOG.md                 # Version history (0.1.0 → 0.1.7)
├── README.md                    # Project overview
├── Dockerfile                   # Backend Docker image
├── docker-compose.yml           # Backend + Frontend containers
├── pyproject.toml               # Python project config (ruff, pytest)
├── requirements.txt             # Python dependencies
└── alembic.ini                  # Alembic config
```

---

## 5. Backend — Cara Kerja Engine

### Engine Registry (18 engines)

Semua engine analisis mengikuti interface yang sama:

```python
class SomeEngine:
    def __init__(self, storage: DataStorage):
        self.storage = storage

    def compute(self, ticker: str) -> dict:
        """Return {'score': 0-100, 'breakdown': {...}, 'as_of': timestamp}"""
        ...
```

| # | Engine | File | Fungsi |
|---|--------|------|--------|
| 1 | Technical | `analysis/technical.py` | RSI, MACD, MA20/50, Bollinger Bands |
| 2 | Fundamental | `analysis/fundamental.py` | P/E, P/B, ROE, debt ratio, growth |
| 3 | Macro | `analysis/macro.py` | Interest rate, inflation, GDP growth |
| 4 | Global Market | `analysis/global_market.py` | S&P500, Nikkei, Hang Seng correlation |
| 5 | Sentiment | `sentiment/engine.py` | Indonesian NLP dari RSS news |
| 6 | Foreign Flow | `sentiment/foreign_flow.py` | Net buy/sell asing |
| 7 | Broker Summary | `sentiment/broker_summary.py` | Smart money tracking |
| 8 | Social Media | `sentiment/social_media.py` | Reddit + X/Twitter sentiment |
| 9 | Google Trends | `sentiment/google_trends.py` | Search volume trend |
| 10 | Market Relationship | `intelligence/relationship.py` | Cross-asset correlation + lag |
| 11 | Corporate Actions | `corporate/actions.py` | Split, dividend, adjustment factor |
| 12 | Regime Detection | `analysis/regime.py` | Trending/neutral/volatile/shock |
| 13 | Red Flags | `analysis/red_flags.py` | Earnings quality, governance, balance sheet |
| 14 | Screener | `analysis/screener.py` | Technical/momentum/value templates |
| 15 | Risk Engine | `risk/engine.py` | VaR, CVaR, position sizing |
| 16 | Kelly Criterion | `risk/kelly.py` | Half/quarter Kelly position sizing |
| 17 | Decision Engine | `decision/engine.py` | Weighted multi-factor scoring |
| 18 | AI Learning | `ai_learning/engine.py` | Linear Regression weight optimization |

### Decision Engine — Cara Kerja

```python
# Bobot default (bisa dioptimasi oleh AI Learning Engine)
DEFAULT_WEIGHTS = {
    "technical": 0.20,
    "fundamental": 0.15,
    "macro": 0.10,
    "global_market": 0.10,
    "sentiment": 0.15,
    "foreign_flow": 0.10,
    "broker_summary": 0.05,
    "social_media": 0.05,
    "google_trends": 0.05,
    "relationship": 0.05,
}

# Conviction score = weighted sum of all engine scores
# Action logic:
#   conviction >= 70 → BUY
#   conviction < 40  → SELL (exit if holding)
#   otherwise        → HOLD
```

### Execution Engine — Cara Kerja

```
1. Ambil daftar ticker (dari watchlist atau argumen)
2. Untuk setiap ticker:
   a. Compute scores via AnalysisPipeline
   b. Get recommendation dari DecisionEngine
   c. Jika BUY dan auto_trade_enabled:
      - Hitung position size (Risk Engine)
      - Round ke lot IDX (100 lembar)
      - Round harga ke tick size BEI
      - Simpan order ke database
   d. Jika SELL dan ada posisi terbuka:
      - Cek stop-loss, take-profit, trailing stop
      - Cek conviction < EXIT_CONVICTION_THRESHOLD
      - Eksekusi sell order
3. Update portfolio state
4. Kirim Telegram notification (jika dikonfigurasi)
```

### Data Quality Validation

Setiap data OHLCV yang di-fetch divalidasi dengan scoring:

| Tier | Score | Action | Arti |
|------|-------|--------|------|
| A | ≥ 0.95 | OK | Data bersih, langsung simpan |
| B | 0.80–0.95 | OK | Data acceptable, simpan dengan warning |
| C | 0.60–0.80 | Delayed | Anomali terdeteksi, review manual |
| Fail | < 0.60 | Pause | Data rusak, jangan simpan |

---

## 6. Frontend — Halaman & Komponen

### Halaman

| Route | File | Fungsi |
|-------|------|--------|
| `/` | `page.tsx` | Redirect ke `/dashboard` |
| `/dashboard` | `dashboard/page.tsx` | Main page: chart, scores, recommendation, execution log, rebalance panel, performance analytics, watchlist |
| `/audit` | `audit/page.tsx` | Audit log viewer (filter by event_type, actor) |
| `/backtest` | `backtest/page.tsx` | Run backtest (POST), tampilkan hasil metrics |
| `/portfolio` | `portfolio/page.tsx` | Open positions + portfolio exposure summary |
| `/engines` | `engines/page.tsx` | Engine registry — daftar 18 engine dengan status |

### Komponen Shared

| Komponen | File | Fungsi |
|----------|------|--------|
| `TerminalLayout` | `components/TerminalLayout.tsx` | Sidebar navigation + dark theme layout |
| `PriceChart` | `components/PriceChart.tsx` | Candlestick chart (lightweight-charts) |

### Frontend → Backend Communication

Semua halaman menggunakan `NEXT_PUBLIC_API_BASE` environment variable:

```typescript
// .env.local
NEXT_PUBLIC_API_BASE=http://localhost:8000

// Di kode:
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const res = await fetch(`${API_BASE}/api/scores/${ticker}`);
```

### UI Design

- **Theme:** Terminal/dark mode (zinc-900 background, monospace font)
- **Chart library:** Recharts (bar, area) + lightweight-charts (candlestick)
- **CSS:** Tailwind CSS 4
- **Framework:** Next.js 16, React 19

---

## 7. Database — Skema & Tabel

Database: **SQLite** (`data/trading_system.db`), 32 tabel.

### Tabel Utama

| Tabel | Fungsi | Key columns |
|-------|--------|-------------|
| `ohlcv` | Price data (OHLCV + adjusted_close) | ticker, timestamp, timeframe |
| `scores` | Multi-factor scores per ticker | ticker, engine, score, as_of |
| `positions` | Open/closed positions | ticker, quantity, avg_entry_price, status |
| `orders` | Order history | ticker, order_type, quantity, price, status |
| `audit_log` | Audit trail (all actions) | event_type, payload, timestamp, actor |
| `watchlist` | Favorite tickers | ticker, is_favorite, notes |
| `system_state` | Key-value runtime flags | key, value, updated_at |
| `ai_weights` | AI-optimized factor weights | ticker, weights_json, r2_score |
| `equity_snapshots` | Daily equity for charting | date, equity, cash, positions_value |
| `daily_risk_metrics` | VaR, CVaR, drawdown per day | date, var_95, var_99, max_drawdown |
| `relationship_matrix` | Cross-asset correlation | asset_a, asset_b, window, correlation |
| `corporate_actions` | Split, dividend | ticker, action_type, ex_date, value |
| `source_health` | Data source health | source, last_success, last_error, status |
| `news` | News articles for sentiment | ticker, source, sentiment_score |

### Tabel Tambahan (legacy/imported)

`broker_flow`, `foreign_flow`, `dividends`, `esg_scores`, `external_events`,
`fear_greed`, `fundamental_data`, `instrument_master`, `macro_data`,
`market_calendar`, `pattern_analysis`, `policy_events`, `sector_master`,
`stock_personality`, `technical_indicators`, `trade_journal`,
`valuation_cache`

### CRUD Operations

`DataStorage` (`src/trading_system/data/storage.py`) menyediakan:

- **Create:** `save_ohlcv`, `save_score`, `save_position`, `save_order`, `save_ai_weights`, `save_equity_snapshot`, `save_daily_risk_metrics`, `save_corporate_action`, `save_relationship`, `add_to_watchlist`, `audit`, `set_state`
- **Read:** `load_ohlcv`, `load_scores`, `get_open_position`, `get_all_open_positions`, `get_open_position_by_id`, `get_orders`, `get_audit_logs`, `get_ai_weights`, `get_equity_snapshots`, `get_daily_risk_metrics`, `get_source_health`, `get_state`, `list_tickers`
- **Update:** `update_position`, `update_adjusted_close`, `update_source_health`, `update_watchlist`, `toggle_watchlist`, `set_state`
- **Delete:** `delete_ohlcv`, `delete_scores`, `delete_orders`, `delete_audit_logs`, `delete_position`, `delete_ai_weights`, `delete_equity_snapshots`, `delete_daily_risk_metrics`, `delete_relationships`, `delete_corporate_actions`, `delete_news`

---

## 8. API — Endpoint Reference Cepat

**Base URL:** `http://localhost:8000`
**Swagger docs:** `http://localhost:8000/docs`
**Total:** 63 REST endpoints + 1 WebSocket

### Read (GET) — tidak butuh API key di dev mode

| Endpoint | Fungsi |
|----------|--------|
| `GET /` | Root — status check |
| `GET /api/health` | System health (data source status) |
| `GET /api/tickers` | List all tickers (paginated) |
| `GET /api/data/{category}?ticker=X` | OHLCV data (paginated) |
| `GET /api/indicators/{ticker}` | OHLCV + technical indicators |
| `GET /api/scores/{ticker}` | Multi-factor scores |
| `GET /api/recommend/{ticker}` | BUY/HOLD/SELL recommendation |
| `GET /api/explain/{ticker}` | AI narrative explanation |
| `GET /api/monitor` | System health monitor |
| `GET /api/positions` | All open positions |
| `GET /api/positions/{ticker}` | Position for specific ticker |
| `GET /api/portfolio/exposure` | Portfolio exposure summary |
| `GET /api/orders` | Order history |
| `GET /api/execution/logs` | Execution logs (orders + audit) |
| `GET /api/execution/toggle` | Auto-trade toggle status |
| `GET /api/rebalance/status` | Rebalance status & drift |
| `GET /api/rebalance/toggle` | Rebalance toggle status |
| `GET /api/performance` | Portfolio performance metrics |
| `GET /api/watchlist` | Favorite tickers |
| `GET /api/audit` | Audit log (filter + paginate) |
| `GET /api/system-state/{key}` | System state value |
| `GET /api/factor-weights/{ticker}` | AI factor weights |
| `GET /api/corporate/{ticker}` | Corporate actions |
| `GET /api/relationship/{ticker}` | Market relationship |
| `GET /api/engines` | Engine registry (18 engines) |

### Write (POST) — butuh API key jika API_KEY set

| Endpoint | Fungsi |
|----------|--------|
| `POST /api/fetch` | Fetch & store OHLCV data |
| `POST /api/scores/compute` | Compute scores for ticker |
| `POST /api/recommend` | Custom-weighted recommendation |
| `POST /api/paper-trade` | Simulate paper trade |
| `POST /api/backtest` | Run backtest |
| `POST /api/backtest/monte-carlo` | Monte Carlo simulation |
| `POST /api/backtest/walk-forward` | Walk-forward analysis |
| `POST /api/execution/run` | Manual execution cycle |
| `POST /api/execution/toggle` | Toggle auto-trade on/off |
| `POST /api/rebalance` | Trigger manual rebalance |
| `POST /api/rebalance/toggle` | Toggle rebalance on/off |
| `POST /api/performance/snapshot` | Save equity snapshot |

### Update (PATCH/PUT) — butuh API key

| Endpoint | Fungsi |
|----------|--------|
| `PATCH /api/positions/{id}` | Update position (stop_loss, take_profit, status) |
| `PUT /api/watchlist/{ticker}` | Update watchlist (notes, is_favorite) |
| `PUT /api/system-state/{key}` | Set system state value |

### Delete (DELETE) — butuh API key (selalu sensitive)

| Endpoint | Fungsi |
|----------|--------|
| `DELETE /api/data/{ticker}` | Delete OHLCV data |
| `DELETE /api/scores/{ticker}` | Delete scores |
| `DELETE /api/orders` | Delete orders (optional filter) |
| `DELETE /api/audit` | Delete audit logs (optional filter) |
| `DELETE /api/positions/{id}` | Delete position |
| `DELETE /api/ai/weights` | Delete AI weights |
| `DELETE /api/performance/snapshots` | Delete equity snapshots |
| `DELETE /api/risk/daily` | Delete daily risk metrics |
| `DELETE /api/archive/{ticker}` | Delete Parquet archive files |
| `DELETE /api/relationships` | Delete relationship matrix |
| `DELETE /api/corporate-actions/{ticker}` | Delete corporate actions |
| `DELETE /api/news` | Delete news entries |

### WebSocket

| Endpoint | Fungsi |
|----------|--------|
| `WS /ws/live` | Real-time engine status updates |

### Security

- **API Key:** Set `API_KEY` di `.env`. Semua endpoint (kecuali `/` dan `/api/health`) butuh header `X-API-Key`.
- **Production:** `ENV=production` mewajibkan API_KEY non-kosong (fail-fast saat startup).
- **Sensitive endpoints:** DELETE methods, execution toggle, rebalance, fetch — selalu butuh API key.
- **Rate limiting:** 60 requests/minute per IP (configurable via `RATE_LIMIT_MAX`).
- **CORS:** Configurable via `CORS_ORIGINS` env var.

---

## 9. CLI — Command Line Interface

**Entry point:** `python -m trading_system.cli <command> [args]`

| Command | Fungsi | Contoh |
|---------|--------|--------|
| `fetch` | Download & validate OHLCV | `cli fetch BBCA.JK TLKM.JK --period 2y` |
| `list` | List tickers in DB | `cli list` |
| `compute-scores` | Hitung semua factor scores | `cli compute-scores BBCA.JK` |
| `recommend` | Generate recommendation | `cli recommend BBCA.JK` |
| `explain` | Explain recommendation | `cli explain BBCA.JK` |
| `backtest` | Run backtest | `cli backtest BBCA.JK --strategy ma_crossover` |
| `backtest` + MC | Monte Carlo simulation | `cli backtest BBCA.JK --monte-carlo --n-simulations 1000` |
| `backtest` + WF | Walk-forward analysis | `cli backtest BBCA.JK --walk-forward --n-splits 5` |
| `corporate-actions` | Fetch corporate actions | `cli corporate-actions BBCA.JK` |
| `update-adjusted-close` | Recompute adjusted_close | `cli update-adjusted-close BBCA.JK` |
| `import-legacy` | Import dari legacy DB | `cli import-legacy --source path/to/saham.db` |
| `relationship` | Cross-asset correlation | `cli relationship BBCA.JK --window 60` |
| `monitor` | System health check | `cli monitor` |
| `paper-trade` | Simulate paper trade | `cli paper-trade BBCA.JK` |
| `execution` | Run automated execution | `cli execution --interval 15` |
| `execution --once` | Run one cycle | `cli execution --once --tickers BBCA.JK` |
| `test-e2e` | End-to-end pipeline test | `cli test-e2e --tickers BBCA.JK TLKM.JK` |

---

## 10. Konfigurasi & Environment

### File `.env`

Copy `.env.example` ke `.env` dan edit:

```bash
cp .env.example .env
```

### Environment Variables

| Variable | Default | Fungsi |
|----------|---------|--------|
| `TELEGRAM_BOT_TOKEN` | — | Telegram bot token untuk notifikasi |
| `TELEGRAM_CHAT_ID` | — | Telegram chat ID |
| `DAILY_RUNNER_TICKERS` | `BBCA.JK,TLKM.JK,...` | Ticker untuk daily job |
| `DAILY_RUNNER_TIME` | `17:00` | Waktu daily job |
| `AUTO_TRADE_ENABLED` | `false` | Enable auto-execution (HATI-HATI!) |
| `TRADING_CAPITAL` | `100000000` | Modal trading (Rp) |
| `RISK_PER_TRADE` | `0.01` | Risk per trade (1% default) |
| `EXIT_CONVICTION_THRESHOLD` | `40` | Exit jika conviction < 40 |
| `REBALANCE_ENABLED` | `false` | Enable auto-rebalancing |
| `REBALANCE_FREQUENCY` | `monthly` | daily/weekly/monthly |
| `REBALANCE_TARGET_WEIGHTS` | JSON | Target bobot portfolio |
| `DAILY_LOSS_LIMIT` | `1000000` | Max daily loss (Rp) — circuit breaker |
| `REDDIT_CLIENT_ID` | — | Reddit API (sentiment) |
| `REDDIT_CLIENT_SECRET` | — | Reddit API secret |
| `TWITTER_BEARER_TOKEN` | — | Twitter/X API (sentiment) |
| `DATA_ARCHIVE_DIR` | `data/archive/` | Lokasi Parquet archive |
| `ENV` | `development` | `production` = wajib API_KEY |
| `API_KEY` | — | API key untuk autentikasi |
| `CORS_ORIGINS` | `localhost:3000` | Allowed CORS origins |
| `RATE_LIMIT_MAX` | `60` | Max requests per 60s per IP |

### Frontend `.env.local`

```bash
# frontend/.env.local
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

### Config Python (`src/trading_system/config.py`)

Konstanta penting:
- `TRADING_CAPITAL` — modal trading (bisa override via env)
- `IDX_LOT_SIZE` — 100 lembar per lot (Bursa Efek Indonesia)
- `idx_tick_size(price)` — tick size BEI (Rp1 <200, Rp2 <500, Rp5 <2000, Rp10 <5000, Rp25 ≥5000)
- `round_to_tick(price)` — bulatkan ke tick size terdekat
- `DEFAULT_BROKER_FEE_BUY` — 0.15%
- `DEFAULT_BROKER_FEE_SELL` — 0.25% (termasuk PPh 0.1%)
- `EXIT_CONVICTION_THRESHOLD` — 40 (exit jika conviction di bawah ini)

---

## 11. Testing

### Unit Tests (562 tests)

```bash
# Run all tests
python -m pytest tests/unit/ -v

# With coverage
python -m pytest tests/unit/ -v --cov=trading_system --cov-report=term-missing

# Run specific test file
python -m pytest tests/unit/test_api.py -v

# Run with pattern
python -m pytest tests/unit/ -k "test_delete" -v
```

### Test Structure

```
tests/unit/
├── test_api.py              # 39 API endpoint tests (GET, POST, DELETE, PATCH, PUT)
├── test_crud_operations.py  # CRUD delete tests for DataStorage
├── test_technical.py        # Technical analysis engine
├── test_fundamental.py      # Fundamental analysis engine
├── test_backtest.py         # Backtest engine + strategies
├── test_decision.py         # Decision engine
├── test_risk.py             # Risk engine (VaR, position sizing)
├── test_storage.py          # DataStorage CRUD
├── test_validation.py       # Data quality validator
├── test_sentiment.py        # Sentiment NLP engine
├── test_execution.py        # Automated execution engine
├── test_ai_learning.py      # AI weight optimization
├── test_xai.py              # Explainable AI
├── test_corporate.py        # Corporate actions
├── test_relationship.py     # Market relationship
├── test_monitoring.py       # Monitoring engine
├── test_rebalancer.py       # Portfolio rebalancer
├── test_performance.py      # Performance analytics
├── test_paper_trading.py    # Paper trading simulator
├── test_regime.py           # Market regime detection
├── test_kelly.py            # Kelly Criterion
├── test_tax.py              # Indonesia tax calculator
├── test_red_flags.py        # Fundamental red flags
├── test_screener.py         # Stock screener
├── test_archive.py          # Parquet archive adapter
├── test_daily_runner.py     # Daily runner script
├── test_import_legacy.py    # Legacy data import
├── test_pipeline.py         # Analysis pipeline
├── test_config.py           # Config module
└── conftest.py              # Shared fixtures
```

### Linting

```bash
# Python lint (ruff)
python -m ruff check src/trading_system/ tests/unit/

# Python type check (mypy — non-blocking)
python -m mypy src/trading_system/ --ignore-missing-imports

# Frontend lint
cd frontend && npm run lint

# Frontend build
cd frontend && npm run build
```

### E2E Tests (Playwright)

```bash
# Requires running backend + frontend
uvicorn src.trading_system.api.app:app --port 8000 &
cd frontend && npm run dev &
python -m pytest tests/e2e/ -v
```

---

## 12. Deployment

### Docker (Recommended)

```bash
# Build & start all services
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

Services:
- **Backend:** http://localhost:8000
- **Frontend:** http://localhost:3000

### Manual (Production)

**Linux:**
```bash
bash scripts/start_production.sh
```

**Windows:**
```batch
scripts\start_production.bat
```

### Production Checklist

1. Copy `.env.example` ke `.env`, isi semua API keys
2. Set `ENV=production` dan `API_KEY=<strong-key>`
3. Set `AUTO_TRADE_ENABLED=true` HANYA jika siap untuk real trading
4. Run `python -m pytest tests/unit/` — pastikan 562 tests pass
5. Start API: `uvicorn src.trading_system.api.app:app --host 0.0.0.0 --port 8000`
6. Start Execution: `python -m trading_system.cli execution --interval 15`
7. Start Scheduler: `python -m trading_system.cli schedule`
8. (Optional) Start frontend: `cd frontend && npm run build && npm start`

### CI/CD (GitHub Actions)

File: `.github/workflows/ci.yml`

Pipeline (on push to main):
1. **Lint** — ruff check `src/` + `tests/`
2. **Type check** — mypy (non-blocking)
3. **Unit tests** — pytest with coverage (fail if < 50%)
4. **Frontend lint** — ESLint
5. **Frontend build** — Next.js build
6. **Docker build** — Build backend image

---

## 13. Panduan Pengembangan

### Menambah Engine Baru

1. Buat file di `src/trading_system/<kategori>/<nama_engine>.py`
2. Implement interface: `compute(ticker) -> {'score': 0-100, 'breakdown': dict}`
3. Daftarkan di `AnalysisPipeline` (`analysis/pipeline.py`)
4. Tambahkan bobot di `DEFAULT_WEIGHTS` (`decision/engine.py`)
5. Buat test di `tests/unit/test_<nama>.py`
6. Update `docs/STATUS.md` dan `CHANGELOG.md`

### Menambah API Endpoint

1. Tambahkan function di `src/trading_system/api/app.py`
2. Gunakan decorator: `@app.get()`, `@app.post()`, `@app.delete()`, dll.
3. Jika destructive → tambahkan ke `_SENSITIVE_PATHS`
4. Tambahkan test di `tests/unit/test_api.py`
5. Update `docs/API_REFERENCE.md`

### Menambah Frontend Page

1. Buat folder di `frontend/app/<route>/page.tsx`
2. Import `TerminalLayout` dari `../components/TerminalLayout`
3. Gunakan `API_BASE` untuk fetch calls
4. Tambahkan nav link di `TerminalLayout.tsx`
5. Run `npm run lint` dan `npm run build`

### Menambah Database Tabel

1. Tambahkan `CREATE TABLE` di `SCHEMA` (`data/storage.py`)
2. Tambahkan CRUD methods di `DataStorage`
3. Buat migration Alembic jika perlu: `alembic revision --autogenerate -m "description"`
4. Tambahkan test di `tests/unit/test_storage.py`

### Code Style

- **Python:** ruff (line length 100, Python 3.11+ syntax)
- **TypeScript:** ESLint (Next.js config)
- **Imports:** Sorted by ruff (isort rules)
- **No comments** unless explicitly requested
- **Testing:** Write tests before major implementation, never delete tests

### Git Workflow

```bash
# Branch naming
git checkout -b feat/<feature-name>     # new feature
git checkout -b fix/<bug-name>          # bug fix

# Commit message format
type: short description

# Types: feat, fix, docs, refactor, test, chore, ci
# Example: feat: add Kelly Criterion position sizing
```

---

## 14. Dokumentasi Tambahan

| File | Isi | Kapan Baca |
|------|-----|-----------|
| `docs/API_REFERENCE.md` | Detail semua 63 API endpoints dengan parameter & response | Saat integrasi frontend/API |
| `docs/STATUS.md` | Status proyek, metrik (tests, endpoints, tables) | Saat cek progress |
| `docs/SARAN_PENGEMBANGAN.md` | Roadmap pengembangan (1197 lines) | Saat planning sprint |
| `docs/arsitektur-sistem-trading.md` | Deep-dive arsitektur (58K) | Saat perlu memahami detail engine |
| `docs/buku-sistem-trading.md` | Trading system book (86K) | Referensi teori trading |
| `docs/ANALISIS_SUMBER_DATA.md` | Analisis sumber data (MySQL, SQLite, CSV) | Saat import data |
| `docs/MAPPING_PARQUET_SQLITE.md` | Mapping kolom Parquet → SQLite | Saat import legacy data |
| `docs/TEST_PLAN.md` | Strategi testing | Saat menulis test baru |
| `CHANGELOG.md` | Version history (0.1.0 → 0.1.7) | Saat cek apa yang berubah |
| `.env.example` | Template environment variables | Saat setup pertama |

---

## Quick Reference Card

```
# Start backend
.\.venv\Scripts\Activate.ps1
uvicorn src.trading_system.api.app:app --reload --port 8000

# Start frontend
cd frontend && npm run dev

# Run tests
python -m pytest tests/unit/ -q

# Lint
python -m ruff check src/trading_system/ tests/unit/
cd frontend && npm run lint

# Fetch data
python -m trading_system.cli fetch BBCA.JK --period 2y

# Get recommendation
python -m trading_system.cli recommend BBCA.JK

# Run backtest
python -m trading_system.cli backtest BBCA.JK --strategy ma_crossover

# Docker
docker-compose up -d --build
```

---

*Dokumen ini di-generate pada 1 Agustus 2026. Update jika ada perubahan arsitektur atau penambahan fitur.*
