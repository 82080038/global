# Sistem Trading Profesional — Phase 1

Implementasi awal: Data Acquisition, Data Quality Validation, Data Storage, dan Backtesting Engine.

## Struktur

```
src/trading_system/
  data/          # Acquisition, Validation, Storage
  backtest/      # Engine, Strategies, Metrics
  api/           # FastAPI
  cli.py         # CLI runner
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

### Backtest
```bash
python -m trading_system.cli backtest BBCA.JK --strategy buy_and_hold
python -m trading_system.cli backtest BBCA.JK --strategy ma_crossover
```

### API
```bash
python -m trading_system.api.app
# atau
uvicorn trading_system.api.app:app --reload
```

Endpoints:
- `GET /api/health`
- `GET /api/data/ohlcv?ticker=BBCA.JK`
- `POST /api/fetch` {"tickers": ["BBCA.JK"], "period": "2y"}
- `POST /api/backtest` {"ticker": "BBCA.JK", "strategy": "buy_and_hold"}

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

- [ ] Copy `.env.example` to `.env` and fill in API keys
- [ ] Run `python -m trading_system.cli fetch BBCA.JK TLKM.JK ASII.JK` to seed data
- [ ] Run `python -m pytest tests/unit/` to verify all tests pass
- [ ] Start API: `uvicorn src.trading_system.api.app:app --host 0.0.0.0 --port 8000`
- [ ] Start Execution: `python -m trading_system.cli execution --interval 15`
- [ ] Start Scheduler: `python -m trading_system.cli schedule`
- [ ] (Optional) Use `bash scripts/start_production.sh` to start all at once
- [ ] (Optional) Use `docker-compose up -d --build` for containerized deployment
