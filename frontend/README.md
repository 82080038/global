# Frontend Dashboard — Sistem Trading Profesional

Terminal-style dashboard untuk Sistem Trading Profesional (IDX).

## Tech Stack

- **Next.js** (App Router) + TypeScript
- **TailwindCSS** — terminal/zinc dark theme
- **Recharts** — price charts & equity curves
- **FastAPI backend** — http://localhost:8000

## Pages

- `/` — Home / ticker selector
- `/dashboard` — Main dashboard (charts, scores, recommendation, execution logs, rebalance panel, toggle switches)
- `/engines` — Engine registry monitor

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

## API Proxy

The frontend proxies `/api/*` requests to the FastAPI backend at `http://localhost:8000`.

See `next.config.ts` for rewrite rules.

## Build

```bash
npm run build
npm start
```
