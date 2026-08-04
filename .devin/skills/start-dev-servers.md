# Start Dev Servers

## Prerequisites

- Python 3.12 via `.venv/` (virtualenv in repo root)
- `.env` exists with correct paths (copy from `.env.example`)
- Key env vars: `API_KEY=dev-secret-key-2026`, `DATA_ARCHIVE_DIR`, `DATA_RAW_DIR`, `TRADING_CAPITAL`, `RISK_PER_TRADE`, `AUTO_TRADE_ENABLED`

## Backend (FastAPI)

```bash
# From repo root, using venv
ENV=development API_KEY=dev-secret-key-2026 .venv/bin/uvicorn trading_system.api.app:app --port 8000 --log-level warning
```

Backend runs on `http://localhost:8000`.

Verify: `curl -s -H "X-API-Key: dev-secret-key-2026" http://localhost:8000/api/health`

## Frontend (Next.js)

```bash
# From repo root
cd frontend && npm run dev
```

Frontend runs on `http://localhost:3000`.

Frontend `.env.local` must contain:
```
NEXT_PUBLIC_API_BASE=http://localhost:8000
NEXT_PUBLIC_API_KEY=dev-secret-key-2026
```

## CLI (alternative)

```bash
.venv/bin/python -m trading_system.cli schedule
.venv/bin/python -m trading_system.cli list
.venv/bin/python -m trading_system.cli compute-scores BBCA.JK
```

## Stop servers

```bash
pkill -f "uvicorn trading_system"
# Frontend: Ctrl+C in its terminal
```

## Environment

Ensure `.env` exists (copy from `.env.example`). Key vars:
- `API_KEY`, `CORS_ORIGINS`
- `TRADING_CAPITAL`, `RISK_PER_TRADE`, `AUTO_TRADE_ENABLED`
- `DATA_ARCHIVE_DIR`, `DATA_RAW_DIR` (Parquet paths)
- `DAILY_RUNNER_TIME`, `DAILY_RUNNER_ONCE`
- `NEXT_PUBLIC_API_BASE`, `NEXT_PUBLIC_API_KEY` (for frontend)
