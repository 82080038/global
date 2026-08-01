# Start Dev Servers

## Backend (FastAPI)

```bash
uvicorn src.trading_system.api.app:app --reload --host 0.0.0.0 --port 8000
```

Or via CLI:

```bash
python -m trading_system.cli schedule
```

## Frontend (Next.js)

```bash
cd frontend
npm run dev
```

Frontend runs on `http://localhost:3000`, backend on `http://localhost:8000`.

## Environment

Ensure `.env` exists (copy from `.env.example`). Key vars:
- `TRADING_CAPITAL`, `RISK_PER_TRADE`, `AUTO_TRADE_ENABLED`
- `API_KEY`, `CORS_ORIGINS`
- `NEXT_PUBLIC_API_BASE`, `NEXT_PUBLIC_API_KEY`
