# API & Frontend Conventions

## Backend (FastAPI)

- **Entry point**: `src/trading_system/api/app.py`
- **Auth**: API key via `API_KEY` env var (optional in development, required in production)
- **CORS**: configured via `CORS_ORIGINS` env var (default: `localhost:3000`)
- **Rate limiting**: `RATE_LIMIT_MAX` requests per IP per 60 seconds

## Frontend (Next.js + TypeScript)

- **Location**: `frontend/`
- **See**: `frontend/AGENTS.md` for Next.js-specific rules
- **API base URL**: `NEXT_PUBLIC_API_BASE` env var (default: `http://localhost:8000`)
- **API key**: `NEXT_PUBLIC_API_KEY` must match backend `API_KEY` if set

## Guidelines

- Do not hardcode API URLs — use env vars.
- Do not expose API keys in client-side code unless via `NEXT_PUBLIC_*` vars.
- Follow existing patterns for endpoint registration and error handling.
