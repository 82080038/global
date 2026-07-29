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

```bash
cd /opt/lampp/htdocs/global
python3 -m venv venv
source venv/bin/activate
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
