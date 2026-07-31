# Sistem Trading Profesional — Multi-Phase

Sistem operasi pengambilan keputusan investasi berbasis Multi-Factor Analysis, Risk Management, Sentiment Analysis, dan Explainable AI untuk saham Indonesia (IDX).

## Struktur

```
src/trading_system/
  data/           # Acquisition, Validation, Storage, Seeder, Contracts
  analysis/       # Technical, Fundamental, Macro, Global Market, Pipeline
  sentiment/      # Engine (NLP), Foreign Flow, Broker Summary, Social Media, Google Trends
  intelligence/   # Market Relationship (cross-asset correlation)
  corporate/      # Corporate Actions (split, dividend)
  backtest/       # Engine, Strategies, Metrics (Monte Carlo, Walk-Forward)
  risk/           # Risk Engine (VaR, CVaR, position sizing, drawdown)
  portfolio/      # Engine, Performance Analytics, Rebalancer
  execution/      # Manual + Automated Execution Engine (robot trader)
  decision/       # Decision Engine (multi-factor weighted scoring)
  ai_learning/    # AI Learning Engine (Linear Regression weight optimization)
  xai/            # Explainable AI Engine
  monitoring/     # System Health Monitor
  paper_trading/  # Paper Trading Simulator
  api/            # FastAPI REST API + WebSocket
  utils/          # Telegram Notifier
  cli.py          # CLI runner
  config.py       # Global configuration
```

## Install

### Windows (PowerShell)

```powershell
cd C:\xampp\htdocs\global
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Linux / macOS

```bash
cd /opt/lampp/htdocs/global
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
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
- [ ] Run `python -m pytest tests/unit/` to verify all 562 tests pass
- [ ] Start API: `uvicorn src.trading_system.api.app:app --host 0.0.0.0 --port 8000`
- [ ] Start Execution: `python -m trading_system.cli execution --interval 15`
- [ ] Start Scheduler: `python -m trading_system.cli schedule`
- [ ] (Linux) Use `bash scripts/start_production.sh` to start all at once
- [ ] (Windows) Use `scripts\start_production.bat` to start all at once
- [ ] (Optional) Use `docker-compose up -d --build` for containerized deployment

## Testing

```bash
# Unit tests (562 tests)
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
- **[docs/API_REFERENCE.md](docs/API_REFERENCE.md)** — Detail semua 63 API endpoints
- **[docs/STATUS.md](docs/STATUS.md)** — Status proyek dan metrik
- **[docs/SARAN_PENGEMBANGAN.md](docs/SARAN_PENGEMBANGAN.md)** — Roadmap pengembangan
- **[CHANGELOG.md](CHANGELOG.md)** — Version history

## Key Features

- **Multi-Factor Analysis**: Technical, Fundamental, Macro, Global Market, Sentiment, Corporate Actions, Market Relationship
- **Sentiment Engine**: Indonesian NLP (RSS feeds), Foreign Net Flow, Broker Summary (smart money), Social Media (Reddit + X/Twitter), Google Trends
- **Risk Management**: VaR, CVaR, Max Drawdown, position sizing, daily loss limit circuit breaker
- **Automated Execution**: Robot trader with stop-loss, take-profit, trailing stop, monitoring mode
- **Portfolio Rebalancer**: Target weights with drift detection, runtime toggle via API
- **Runtime Toggles**: Auto-trade and rebalance can be toggled on/off via API without server restart
- **AI Learning**: Linear Regression weight optimization from historical score-return pairs
- **Explainable AI**: Narrative explanation with top contributing factors
- **Backtesting**: Buy & Hold, MA Crossover, Monte Carlo simulation, Walk-forward analysis
- **Frontend Dashboard**: Terminal-style UI with charts, scores, recommendations, execution logs, toggle switches
