# API Reference — Trading System

> **Base URL:** `http://127.0.0.1:8000`  
> **Framework:** FastAPI + Uvicorn  
> **Format:** JSON  
> **WebSocket:** `ws://127.0.0.1:8000/ws/live`

---

## System & Data

### GET `/`

Status dan versi aplikasi.

```json
{"status": "ok", "version": "0.1.8"}
```

### GET `/api/health`

Health check semua sumber data.

```json
[
  {"source": "yahoo_finance", "last_success": "2026-07-31T10:00:00", "last_error": null, "status": "ok"}
]
```

### GET `/api/tickers`

Daftar semua ticker di database.

```json
{"tickers": ["BBCA.JK", "TLKM.JK", "ASII.JK"], "count": 3}
```

### GET `/api/data/{category}?ticker=BBCA.JK&start=2026-01-01&end=2026-07-31`

Ambil data OHLCV. `category` harus `ohlcv`.

```json
{
  "ticker": "BBCA.JK",
  "count": 250,
  "data": [
    {"timestamp": "2026-01-02", "open": 9050, "high": 9100, "low": 9000, "close": 9075, "volume": 15000000}
  ]
}
```

### GET `/api/indicators/{ticker}`

OHLCV + indikator teknikal (RSI, MACD, MA, Bollinger).

```json
{
  "ticker": "BBCA.JK",
  "count": 250,
  "data": [
    {"timestamp": "2026-07-31", "close": 9050, "rsi": 55.3, "macd": -12.5, "ma20": 9020, "ma50": 8980, "bb_upper": 9200, "bb_lower": 8800}
  ]
}
```

### POST `/api/fetch`

Fetch dan simpan data dari Yahoo Finance.

**Request:**
```json
{"tickers": ["BBCA.JK", "TLKM.JK"], "period": "2y"}
```

**Response:**
```json
{
  "results": [
    {"ticker": "BBCA.JK", "rows": 500, "quality": 98.5, "tier": "clean", "action": "accept"},
    {"ticker": "TLKM.JK", "rows": 500, "quality": 95.0, "tier": "clean", "action": "accept"}
  ]
}
```

### GET `/api/sentiment/{ticker}`

Sentiment analysis dari NLP berita Indonesia.

```json
{
  "status": "ok",
  "engine": "sentiment",
  "ticker": "BBCA.JK",
  "score": 62.5,
  "sentiment": 0.25,
  "news_count": 5,
  "breakdown": {"positive_words": 12, "negative_words": 3, "articles_matched": 5}
}
```

---

## Analysis & Decision

### GET `/api/scores/{ticker}`

Ambil skor tersimpan per ticker.

```json
{
  "ticker": "BBCA.JK",
  "computed": true,
  "scores": {"technical": 72.5, "fundamental": 65.0, "macro": 55.0, "global": 60.0, "relationship": 50.0, "sentiment": 62.5},
  "details": [
    {"engine": "technical", "score": 72.5, "as_of": "2026-07-31T10:00:00"}
  ]
}
```

### POST `/api/scores/compute`

Hitung skor semua engine untuk ticker.

**Request:**
```json
{"ticker": "BBCA.JK", "period": "2y"}
```

**Response:**
```json
{
  "status": "ok",
  "ticker": "BBCA.JK",
  "scores": {"technical": 72.5, "fundamental": 65.0, "macro": 55.0, "global": 60.0, "relationship": 50.0, "sentiment": 62.5}
}
```

### GET `/api/corporate/{ticker}`

Fetch aksi korporasi (split, dividend).

```json
{
  "status": "ok",
  "ticker": "BBCA.JK",
  "actions": [
    {"action_type": "dividend", "ex_date": "2026-06-15", "value": 50.0, "unit": "IDR_per_share"}
  ]
}
```

### GET `/api/relationship/{ticker}?window=60`

Hitung korelasi dengan aset global/macro.

```json
{
  "status": "ok",
  "ticker": "BBCA.JK",
  "correlations": {"US10Y": -0.15, "GOLD": 0.32, "OIL": 0.18, "USD_IDR": -0.25, "DXY": -0.20}
}
```

### GET `/api/recommend/{ticker}`

Rekomendasi trading lengkap.

```json
{
  "status": "ok",
  "ticker": "BBCA.JK",
  "recommendation": {
    "action": "BUY",
    "conviction": 68.5,
    "composite_score": 62.3,
    "position_size": 0.08,
    "entry_price_range": [8900, 9100],
    "stop_loss": 8750,
    "take_profit": 9500,
    "risk_flags": [],
    "weights_used": {"technical": 0.25, "fundamental": 0.25, "macro": 0.15, "global": 0.15, "relationship": 0.10, "sentiment": 0.10}
  }
}
```

### POST `/api/recommend`

Rekomendasi dengan custom weights.

**Request:**
```json
{"ticker": "BBCA.JK", "weights": {"technical": 0.40, "fundamental": 0.20, "macro": 0.10, "global": 0.10, "relationship": 0.10, "sentiment": 0.10}}
```

### GET `/api/explain/{ticker}`

Penjelasan rekomendasi (XAI).

```json
{
  "status": "ok",
  "ticker": "BBCA.JK",
  "narrative": "Rekomendasi BUY didorong oleh skor teknikal yang kuat (72.5) dan fundamental yang solid (65.0)...",
  "top_factors": [
    {"factor": "technical", "score": 72.5, "contribution": 0.28},
    {"factor": "fundamental", "score": 65.0, "contribution": 0.22}
  ],
  "confidence_interval": [55.0, 70.0]
}
```

### GET `/api/factor-weights/{ticker}?regime=easing`

Factor weights dari AI Learning Engine.

```json
{"ticker": "BBCA.JK", "regime": "easing", "weights": {"technical": 0.15, "fundamental": 0.30, "macro": 0.20, "global": 0.10, "relationship": 0.10, "sentiment": 0.15}}
```

### GET `/api/risk/{ticker}`

Risk analysis per ticker (VaR, position sizing, stop-loss, take-profit, risk flags).

**Query Parameters:**
- `capital` (optional, default: `TRADING_CAPITAL`): Capital for position sizing calculation.

```json
{
  "status": "ok",
  "ticker": "BBCA.JK",
  "var_95": 2.5,
  "var_99": 3.8,
  "position_size": 0.08,
  "stop_loss": 8750,
  "take_profit": 9500,
  "slippage": 0.0005,
  "risk_flags": [],
  "avg_daily_volume": 12500000
}
```

### POST `/api/risk/refresh`

Recalculate dan simpan daily portfolio risk metrics.

```json
{"status": "ok", "date": "2026-07-31", "var_95": 2.5, "var_99": 3.8, "max_drawdown": -5.2}
```

---

## Execution & Orders

### GET `/api/positions`

Semua posisi terbuka.

```json
{"positions": [{"ticker": "BBCA.JK", "quantity": 1000, "entry_price": 9000, "stop_loss": 8750, "take_profit": 9500, "status": "open"}], "count": 1}
```

### GET `/api/portfolio/exposure`

Ringkasan exposure portfolio: cash, invested, total equity, exposure %.

```json
{
  "cash": 50000,
  "invested": 500000,
  "total_equity": 550000,
  "exposure_pct": 90.91,
  "position_count": 1
}
```

### GET `/api/positions/{ticker}`

Posisi untuk ticker spesifik.

### PATCH `/api/positions/{position_id}`

Update position fields (stop_loss, take_profit, trailing_stop_pct, status, current_price, etc.).

**Request:**
```json
{"stop_loss": 8500, "take_profit": 10000}
```

**Response:**
```json
{"position_id": 1, "updated": true, "fields": ["stop_loss", "take_profit"]}
```

### PUT `/api/watchlist/{ticker}`

Update watchlist entry (notes, is_favorite).

**Request:**
```json
{"notes": "Watch for breakout above 9500"}
```

### PUT `/api/system-state/{key}`

Set a system state key-value pair (e.g., circuit breaker flags).

**Request:**
```json
{"value": "HALT"}
```

### GET `/api/system-state/{key}`

Get a system state value by key. Returns 404 if key not found.

```json
{"key": "circuit_breaker", "value": "HALT"}
```

### GET `/api/orders?ticker=BBCA.JK&limit=100`

Riwayat order.

```json
{"orders": [{"id": 1, "ticker": "BBCA.JK", "order_type": "BUY", "shares": 1000, "price": 9000, "total_value": 9000000, "fee": 13500, "status": "filled", "created_at": "2026-07-31T10:00:00"}], "count": 1}
```

### POST `/api/execution/run`

Jalankan satu siklus execution manual. Accepts empty body or optional `{"tickers": [...]}`.

**Response:**
```json
{"results": [{"ticker": "BBCA.JK", "action": "BUY", "shares": 800, "price": 9050, "status": "executed"}], "count": 1}
```

### GET `/api/execution/logs?limit=20`

Log execution (orders + audit events).

```json
{
  "orders": [{"id": 1, "ticker": "BBCA.JK", "order_type": "BUY", "shares": 1000, "price": 9000, "status": "filled", "created_at": "2026-07-31T10:00:00"}],
  "audit_events": [{"event_id": 5, "event_type": "execution", "payload": "{\"action\": \"BUY\"}", "timestamp": "2026-07-31T10:00:00", "actor": "system"}],
  "count": 2
}
```

### GET `/api/execution/toggle`

Status toggle auto-trade.

```json
{"auto_trade_enabled": false, "capital": 100000000, "risk_per_trade": 0.01, "daily_loss_limit": 1000000}
```

### POST `/api/execution/toggle`

Toggle auto-trade on/off (runtime, no restart).

**Request:**
```json
{"enabled": true}
```

**Response:**
```json
{"auto_trade_enabled": true, "capital": 100000000, "risk_per_trade": 0.01, "message": "Auto-trade ENABLED."}
```

---

## Portfolio & Rebalance

### POST `/api/rebalance`

Trigger manual rebalance. Accepts empty body (no request body required).

**Response:**
```json
{"status": "ok", "orders": [{"ticker": "BBCA.JK", "action": "BUY", "shares": 200, "price": 9050}], "count": 1}
```

### GET `/api/rebalance/status`

Status rebalance (weights, drift, config).

```json
{
  "rebalance_enabled": false,
  "frequency": "monthly",
  "target_weights": {"BBCA.JK": 0.4, "TLKM.JK": 0.3, "ASII.JK": 0.3},
  "current_weights": {"BBCA.JK": 0.45, "TLKM.JK": 0.25, "ASII.JK": 0.30},
  "drift": {"BBCA.JK": 0.05, "TLKM.JK": -0.05, "ASII.JK": 0.0}
}
```

### GET `/api/rebalance/toggle`

Status toggle rebalance.

```json
{"rebalance_enabled": false, "frequency": "monthly", "target_weights": "{\"BBCA.JK\": 0.4, \"TLKM.JK\": 0.3, \"ASII.JK\": 0.3}"}
```

### POST `/api/rebalance/toggle`

Toggle rebalance on/off (runtime).

**Request:**
```json
{"enabled": true, "frequency": "weekly", "target_weights": {"BBCA.JK": 0.5, "TLKM.JK": 0.5}}
```

**Response:**
```json
{"rebalance_enabled": true, "frequency": "weekly", "message": "Rebalance ENABLED."}
```

---

## Performance Analytics

### GET `/api/performance?period=1M`

Metrik kinerja portofolio.

| Period | Deskripsi |
|--------|-----------|
| `1M` | 1 bulan |
| `3M` | 3 bulan |
| `6M` | 6 bulan |
| `1Y` | 1 tahun |
| `ALL` | Semua data |

```json
{
  "status": "ok",
  "period": "1M",
  "total_return": 0.045,
  "sharpe_ratio": 1.25,
  "max_drawdown": -0.032,
  "win_rate": 0.60,
  "profit_factor": 1.8,
  "average_win": 500000,
  "average_loss": -300000,
  "total_trades": 15,
  "equity_curve": [["2026-07-01", 100000000], ["2026-07-02", 100500000]]
}
```

### POST `/api/performance/snapshot`

Simpan equity snapshot harian manual.

```json
{"status": "ok", "date": "2026-07-31", "equity": 100500000}
```

---

## Watchlist

### GET `/api/watchlist`

Daftar ticker favorit.

```json
{"tickers": ["BBCA.JK", "TLKM.JK"], "count": 2}
```

### GET `/api/watchlist/all`

Full watchlist dengan metadata.

```json
{
  "items": [{"ticker": "BBCA.JK", "is_favorite": 1, "notes": "Bank terbesar", "created_at": "2026-07-01"}],
  "count": 1
}
```

### POST `/api/watchlist/{ticker}`

Toggle status favorit ticker.

```json
{"ticker": "BBCA.JK", "is_favorite": true}
```

---

## Backtest

### POST `/api/backtest`

Jalankan backtest. Strategy: `buy_and_hold`, `ma_crossover`, `conviction`.

**Request:**
```json
{"ticker": "BBCA.JK", "strategy": "conviction", "capital": 100000000}
```

**Response:**
```json
{
  "ticker": "BBCA.JK",
  "strategy": "conviction",
  "final_equity": 115000000,
  "total_return": 15.0,
  "sharpe_ratio": 1.1,
  "max_drawdown": 8.0,
  "win_rate": 60.0,
  "total_trades": 25,
  "equity_curve": [
    {"date": "2024-01-02", "equity": 100000000},
    {"date": "2024-01-03", "equity": 100500000}
  ],
  "metrics": {"total_return": 0.15, "sharpe_ratio": 1.1, "max_drawdown": -0.08, "win_rate": 0.6, "profit_factor": 1.8}
}
```

### POST `/api/backtest/monte-carlo`

Simulasi Monte Carlo.

**Request:**
```json
{"ticker": "BBCA.JK", "n_simulations": 1000}
```

**Response:**
```json
{
  "ticker": "BBCA.JK",
  "n_simulations": 1000,
  "percentile_5": -0.12,
  "percentile_50": 0.05,
  "percentile_95": 0.22,
  "prob_loss": 0.15
}
```

### POST `/api/backtest/walk-forward`

Walk-forward analysis.

**Request:**
```json
{"ticker": "BBCA.JK", "strategy": "ma_crossover", "n_splits": 5}
```

**Response:**
```json
{
  "ticker": "BBCA.JK",
  "strategy": "ma_crossover",
  "splits": [
    {"train_start": "2024-01", "train_end": "2024-12", "test_return": 0.08, "oos_sharpe": 0.9}
  ],
  "avg_oos_return": 0.06,
  "avg_oos_sharpe": 0.85
}
```

---

## Simulation & Monitoring

### POST `/api/paper-trade`

Simulasi paper trade.

**Request:**
```json
{"ticker": "BBCA.JK", "capital": 1000000000}
```

**Response:**
```json
{
  "status": "ok",
  "ticker": "BBCA.JK",
  "action": "BUY",
  "shares": 800,
  "fill_price": 9050,
  "fees": 13575,
  "total_cost": 7253575,
  "pnl": 0
}
```

### GET `/api/monitor`

Status sistem lengkap.

```json
{
  "status": "ok",
  "sources": {"yahoo_finance": "ok"},
  "tickers_in_db": 10,
  "scores_computed": 60,
  "active_alerts": 0,
  "db_size_mb": 5.2
}
```

### GET `/api/engines`

Status semua engine terdaftar.

```json
{
  "engines": [
    {"name": "technical", "status": "healthy", "latency_ms": 12, "latest_score": 72.5, "sample_ticker": "BBCA.JK"},
    {"name": "fundamental", "status": "idle", "latency_ms": 0, "latest_score": null, "sample_ticker": null}
  ],
  "total": 18,
  "healthy": 12,
  "idle": 4,
  "warning": 1,
  "error": 1
}
```

---

## WebSocket

### `ws://host:8000/ws/live`

Real-time engine status + system updates. Mengirim `_build_engines_status()` secara berkala.

**Message format:**
```json
{
  "engines": [...],
  "total": 18,
  "healthy": 12,
  "idle": 4,
  "warning": 1,
  "error": 1,
  "timestamp": "2026-07-31T10:00:00"
}
```

Frontend Engine Monitor (`/engines`) terhubung ke WebSocket ini dengan auto-reconnect setiap 3 detik.

---

## Security

### API Key Authentication

Jika env var `API_KEY` di-set, semua endpoint (kecuali `/` dan `/api/health`) membutuhkan header `X-API-Key`. Endpoint sensitif (toggle, execution, rebalance, fetch, dll.) selalu wajib API key meski di development. DELETE method selalu wajib API key.

```
X-API-Key: your_api_key
```

Jika `API_KEY` kosong (default), autentikasi dinonaktifkan (untuk development).

### CORS

Cross-origin requests diizinkan dari origin yang dikonfigurasi di env var `CORS_ORIGINS` (default: `http://localhost:3000,http://127.0.0.1:3000`).

### Rate Limiting

Setiap IP dibatasi maksimum `RATE_LIMIT_MAX` request per 60 detik (default: 60). Jika melebihi, response `429 Too Many Requests`.

---

## Error Handling

Semua endpoint mengembalikan HTTP status code standar:

| Code | Deskripsi |
|------|-----------|
| 200 | Success |
| 400 | Bad request (missing parameter, invalid value) |
| 401 | Unauthorized (missing or invalid API key) |
| 404 | Not found (ticker tidak ada di DB, data tidak tersedia) |
| 429 | Too many requests (rate limit exceeded) |
| 500 | Internal server error |

**Error response format:**
```json
{"detail": "Ticker not found in database"}
```

---

## Audit Log

### GET `/api/audit`

Get audit log entries with optional filtering and pagination.

**Query Parameters:**
- `event_type` (optional): Filter by event type prefix (e.g., `decision`, `order`)
- `actor` (optional): Filter by actor
- `limit` (default 100): Maximum entries to return
- `offset` (default 0): Pagination offset

```json
{
  "logs": [
    {"event_id": 1, "event_type": "decision.buy", "payload": "{...}", "timestamp": "2026-08-01T10:00:00", "actor": "system"}
  ],
  "count": 1
}
```

---

## DELETE Endpoints (CRUD)

### DELETE `/api/data/{ticker}`

Delete all OHLCV data for a ticker.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timeframe` | str | `"1d"` | Timeframe to delete |

```json
{"ticker": "BBCA.JK", "deleted": 500}
```

### DELETE `/api/scores/{ticker}`

Delete scores for a ticker, optionally filtered by engine.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `engine` | str | `null` | Engine name filter |

### DELETE `/api/orders`

Delete orders, optionally filtered by ticker and/or older than a date.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ticker` | str | `null` | Ticker filter |
| `before_date` | str | `null` | ISO date threshold |

### DELETE `/api/audit`

Delete audit logs, optionally filtered by date and/or event_type prefix.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `before_date` | str | `null` | ISO date threshold |
| `event_type` | str | `null` | Event type prefix filter |

### DELETE `/api/positions/{position_id}`

Delete a position by ID. Returns 404 if not found.

### DELETE `/api/ai/weights`

Delete AI weight entries, optionally filtered by ticker and/or date.

### DELETE `/api/performance/snapshots`

Delete equity snapshots, optionally older than a date.

### DELETE `/api/risk/daily`

Delete daily risk metrics, optionally older than a date.

### DELETE `/api/archive/{ticker}`

Delete all Parquet files for a ticker from the archive.

### DELETE `/api/relationships`

Delete relationship matrix entries, optionally filtered by asset_a.

### DELETE `/api/corporate-actions/{ticker}`

Delete corporate actions for a ticker.

### DELETE `/api/news`

Delete news entries, optionally filtered by source and/or date.
