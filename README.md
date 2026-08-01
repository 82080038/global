# Sistem Trading Profesional — Multi-Phase

Sistem operasi pengambilan keputusan investasi berbasis Multi-Factor Analysis, Risk Management, Sentiment Analysis, dan Explainable AI untuk saham Indonesia (IDX).

## Struktur

```
src/trading_system/
  data/           # Acquisition, Validation, Storage (78 tables), Extended Storage, Archive, Rate Limit, IDX Scraper
  analysis/       # Technical, Advanced Technical, Fundamental (+fallback), Macro, Global Market, Pipeline, Relationship, Regime, Enhanced Regime, Red Flags, Screener, Factor Screener, Factor Engine, Manipulation, No-Trade, Order Book, World Monitor, Liquidity Filter, Pattern Reliability, Attribution, Alpha Composer/Validation, Cross-Asset, Lead-Lag
  sentiment/      # Engine (6 sumber: NLP, Foreign Flow, Broker, Social Media, Google Trends, IDX Historical)
  corporate/      # Corporate Actions (split, dividend)
  backtest/       # Engine, Strategies (Buy&Hold, MA, Conviction), Metrics (Monte Carlo, Walk-Forward)
  risk/           # Risk Engine, Enhanced Risk, Circuit Breaker, Slippage Model, Correlation Sizing, Kelly, Cost Model, Expectancy
  portfolio/      # Engine, Performance Analytics, Rebalancer
  execution/      # Manual + Automated Execution Engine, Broker Adapter (Mock + Sinarmas/BNI), Tax
  decision/       # Decision Engine (multi-factor weighted scoring)
  ai_learning/    # AI Learning Engine, Deep Learning (LSTM), Ensemble, Labeling, Model Registry, Purged TSS, Walk-Forward
  xai/            # Explainable AI Engine
  monitoring/     # System Health Monitor
  paper_trading/  # Paper Trading Simulator
  api/            # FastAPI REST API (78 endpoints) + WebSocket
  utils/          # Telegram Notifier
  cli.py          # CLI runner (15 subcommands)
  config.py       # Global configuration
```

## Install

### Windows (PowerShell)

```powershell
cd C:\xampp\htdocs\global
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

### Linux / macOS

```bash
cd /opt/lampp/htdocs/global
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Using uv (recommended - faster)

```bash
cd /opt/lampp/htdocs/global
uv venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
uv sync
```

## Run

### Fetch data
```bash
python -m trading_system.cli fetch BBCA.JK TLKM.JK --period 2y
```

### Compute scores
```bash
python -m trading_system.cli compute-scores BBCA.JK
```

### Backtest
```bash
python -m trading_system.cli backtest BBCA.JK --strategy buy_and_hold
python -m trading_system.cli backtest BBCA.JK --strategy ma_crossover
python -m trading_system.cli backtest BBCA.JK --strategy conviction
```

### Decision (recommendation + explanation)
```bash
python -m trading_system.cli recommend BBCA.JK
python -m trading_system.cli explain BBCA.JK
```

### Automated execution
```bash
python -m trading_system.cli execution --once
python -m trading_system.cli execution --interval 15
```

### Daily scheduler
```bash
python -m trading_system.cli schedule            # persistent scheduler mode
python -m trading_system.cli schedule --once    # run once and exit (cron mode)
```

### API
```bash
uvicorn src.trading_system.api.app:app --host 0.0.0.0 --port 8000
```

Endpoints:
- `GET /api/health` — system health check
- `GET /api/tickers` — list all tickers in DB (paginated)
- `GET /api/data/{category}?ticker=...` — raw OHLCV data (paginated)
- `GET /api/indicators/{ticker}` — OHLCV + technical indicators
- `GET /api/scores/{ticker}` — multi-factor scores
- `POST /api/scores/compute` — compute scores for a ticker
- `GET /api/recommend/{ticker}` — decision engine recommendation
- `POST /api/recommend` — recommendation with custom weights
- `GET /api/explain/{ticker}` — explainable AI narrative
- `GET /api/sentiment/{ticker}` — news-based sentiment (Indonesian NLP)
- `GET /api/risk/{ticker}` — risk analysis (VaR, position sizing)
- `GET /api/risk/daily` — daily portfolio risk metrics
- `POST /api/risk/refresh` — recalculate daily risk metrics
- `GET /api/performance` — portfolio performance analytics
- `POST /api/performance/snapshot` — save equity snapshot manually
- `GET /api/positions` — all open positions
- `GET /api/positions/{ticker}` — position for a specific ticker
- `GET /api/orders` — order history
- `GET /api/portfolio/exposure` — portfolio exposure summary
- `GET /api/execution/logs` — execution order + audit logs
- `POST /api/execution/run` — run one execution cycle manually
- `GET /api/execution/toggle` — auto-trade toggle status
- `POST /api/execution/toggle` — toggle auto-trade on/off (runtime)
- `GET /api/rebalance/status` — rebalance status & drift
- `POST /api/rebalance` — trigger manual rebalance
- `GET /api/rebalance/toggle` — rebalance toggle status
- `POST /api/rebalance/toggle` — toggle rebalance on/off (runtime)
- `GET /api/watchlist` — favorite tickers
- `POST /api/watchlist/{ticker}` — toggle favorite
- `POST /api/fetch` — fetch & store OHLCV data
- `POST /api/paper-trade` — simulate paper trade
- `GET /api/monitor` — system health & alerts
- `GET /api/factor-weights/{ticker}` — AI learning factor weights
- `POST /api/ai/train` — train AI weights from historical data
- `GET /api/corporate/{ticker}` — corporate actions
- `GET /api/relationship/{ticker}` — market relationship analysis
- `POST /api/backtest` — run backtest (buy_and_hold, ma_crossover, conviction)
- `POST /api/backtest/monte-carlo` — Monte Carlo simulation
- `POST /api/backtest/walk-forward` — walk-forward analysis
- `GET /api/audit` — audit log entries
- `GET /api/engines` — engine registry (54 engines)
- `GET /api/system-state/{key}` — system state value
- `PUT /api/system-state/{key}` — set system state value
- `GET /api/extended/snapshot/{ticker}` — fundamental snapshot from MySQL import
- `GET /api/extended/shareholders/{ticker}` — shareholders data
- `GET /api/extended/directors/{ticker}` — directors & commissioners
- `GET /api/extended/broker-summary` — broker activity summary
- `GET /api/extended/pattern-reliability/{ticker}` — historical pattern win rate
- `GET /api/extended/pattern-candidates` — detected pattern candidates
- `GET /api/extended/advanced-features/{ticker}` — order flow, volume profile
- `GET /api/extended/ai-scores-history/{ticker}` — historical AI scores
- `GET /api/extended/sentiment/{ticker}` — IDX historical sentiment
- `GET /api/extended/market-indices` — market index data (JCI, sectoral)
- `GET /api/extended/financial-statements/{ticker}` — financial statements
- `GET /api/extended/social-media-sentiment/{ticker}` — social media sentiment
- `GET /api/extended/stock-splits/{ticker}` — stock split history
- `GET /api/extended/quarterly-earnings/{ticker}` — quarterly earnings
- `GET /api/extended/circuit-breaker` — circuit breaker status
- `GET /api/replay/list` — list replay results
- `GET /api/replay/{ticker}` — replay detail per ticker
- `WS /ws/live` — WebSocket real-time engine status

## Deployment with Docker

```bash
# Build and start all services
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

Services:
- Backend API: http://localhost:8000
- Frontend Dashboard: http://localhost:3000

Data persists in `./data/` volume mount.

## Production Checklist

- [ ] Copy `.env.example` to `.env` and fill in API keys (Reddit, Twitter, Telegram, etc.)
- [ ] Run `python -m trading_system.cli fetch BBCA.JK TLKM.JK ASII.JK` to seed data
- [ ] Run `python -m pytest tests/unit/` to verify all 600+ tests pass
- [ ] Start API: `uvicorn src.trading_system.api.app:app --host 0.0.0.0 --port 8000`
- [ ] Start Execution: `python -m trading_system.cli execution --interval 15`
- [ ] Start Scheduler: `python -m trading_system.cli schedule`
- [ ] (Linux) Use `bash scripts/start_production.sh` to start all at once
- [ ] (Windows) Use `scripts\start_production.bat` to start all at once
- [ ] (Optional) Use `docker-compose up -d --build` for containerized deployment

## Testing

```bash
# Unit tests (600+ tests)
python -m pytest tests/unit/ -v

# With coverage
python -m pytest tests/unit/ -v --cov=trading_system --cov-report=term-missing

# Lint check (src + tests)
python -m ruff check src/trading_system/ tests/unit/

# Type check (non-blocking)
python -m mypy src/trading_system/ --ignore-missing-imports

# E2E tests (requires Playwright + running servers)
python -m pytest tests/e2e/ -v
```

## Documentation

- **[docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md)** — Panduan lengkap untuk memahami, menggunakan, dan mengembangkan aplikasi (START HERE)
- **[docs/API_REFERENCE.md](docs/API_REFERENCE.md)** — Detail semua 63 API endpoints + 15 extended endpoints
- **[docs/STATUS.md](docs/STATUS.md)** — Status proyek dan metrik
- **[docs/SARAN_PENGEMBANGAN.md](docs/SARAN_PENGEMBANGAN.md)** — Roadmap pengembangan
- **[CHANGELOG.md](CHANGELOG.md)** — Version history

## Key Features

- **Multi-Factor Analysis**: 54 engines — Technical, Advanced Technical, Fundamental (+fallback), Macro, Global Market, Sentiment (6 sources), Corporate Actions, Market Relationship, Pattern Reliability, Liquidity Filter, Manipulation Detection, No-Trade Zone, Order Book, World Monitor, Regime Detection, Factor Engine, Screener, Alpha Composer/Validation, Cross-Asset, Lead-Lag, Performance Attribution
- **Sentiment Engine**: 6 sources — Indonesian NLP (RSS feeds), Foreign Net Flow, Broker Summary (smart money), Social Media (Reddit + X/Twitter), Google Trends, IDX Historical Sentiment
- **Risk Management**: VaR, CVaR, Max Drawdown, position sizing, daily loss limit, Circuit Breaker (IHSG crash halt), Slippage Model (dynamic), Kelly Criterion, Correlation Sizing, Enhanced Risk (vol-targeting, sector caps)
- **Automated Execution**: Robot trader with stop-loss, take-profit, trailing stop, monitoring mode
- **Portfolio Rebalancer**: Target weights with drift detection, runtime toggle via API
- **Runtime Toggles**: Auto-trade and rebalance can be toggled on/off via API without server restart
- **AI Learning**: Linear Regression, Deep Learning (LSTM/MLP), Ensemble, Walk-Forward optimization, Purged TSS
- **Explainable AI**: Narrative explanation with top contributing factors
- **Backtesting**: Buy & Hold, MA Crossover, Conviction strategy, Monte Carlo simulation, Walk-forward analysis
- **Extended Data**: 14 tables imported from MySQL (saham_snapshot, idx_sentiment_data, shareholders, financial statements, pattern reliability, dll)
- **Frontend Dashboard**: 6 pages — Dashboard, Engine Monitor, Backtest, Portfolio, Audit, Replay (terminal-style UI)
