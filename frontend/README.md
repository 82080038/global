# Frontend Dashboard — Sistem Trading Profesional

Terminal-style dashboard untuk Sistem Trading Profesional (IDX).

## Tech Stack

- **Next.js 16** (App Router) + TypeScript + React 19
- **TailwindCSS 4** — terminal/zinc dark theme
- **Recharts** — price charts & equity curves
- **lightweight-charts** — candlestick price chart
- **FastAPI backend** — http://localhost:8000

## Pages

- `/` — Home (redirect ke `/dashboard`)
- `/dashboard` — Main dashboard (charts, scores, recommendation, execution logs, rebalance panel, toggle switches, performance analytics, watchlist)
- `/engines` — Engine registry monitor (18 engines)
- `/audit` — Audit log viewer (filter by event_type, actor)
- `/backtest` — Backtest runner (POST, tampilkan metrics + equity curve)
- `/portfolio` — Portfolio positions + exposure summary

## Dashboard Features

- Candlestick price chart with RSI, MACD, MA, Bollinger Bands
- Multi-factor score table (technical, fundamental, macro, global, sentiment, relationship)
- Decision engine recommendation with conviction score
- Explainable AI narrative + top factors
- Execution log (orders + audit events) with auto-refresh
- **Auto-Trade toggle** (green/red switch in Execution Log header)
- **Rebalance toggle** (purple/gray switch in Rebalancing panel)
- Portfolio performance analytics (return, Sharpe, drawdown, win rate, equity curve)
- Watchlist with favorite toggle
- System health footer (status, tickers, scores, alerts)

## Getting Started

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

## API Configuration

Frontend menggunakan environment variable `NEXT_PUBLIC_API_BASE` untuk koneksi ke backend:

```bash
# frontend/.env.local
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

Semua fetch calls menggunakan `${API_BASE}/api/...` pattern.

## Build

```bash
npm run build
npm start
```

## Lint

```bash
npm run lint
```
