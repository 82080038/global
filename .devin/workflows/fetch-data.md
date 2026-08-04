# Workflow: Fetch & Update Data

## Purpose
Fetch latest OHLCV data from Yahoo Finance, update technical indicators, and sync to Parquet.

## Steps

### 1. Check market status first

```bash
curl -s -H "X-API-Key: dev-secret-key-2026" http://localhost:8000/api/market-status | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f'Market open: {d[\"is_open\"]}, Trading day: {d[\"is_trading_day\"]}')
print(f'Session: {d[\"session\"]}, Next open: {d[\"next_open\"]}')
"
```

### 2. Fetch OHLCV data for all listed equity tickers

```bash
# Fetch all tickers (equity only — non-equity fetched separately as reference)
.venv/bin/python -m trading_system.cli fetch --all

# Or fetch specific ticker
.venv/bin/python -m trading_system.cli fetch --ticker BBCA.JK
```

### 3. Fetch IDX real-data (foreign flow & broker summary)

```bash
# Foreign flow from idx.co.id
.venv/bin/python -m trading_system.cli fetch-idx-foreign-flow --start 2026-01-01

# Broker summary from idx.co.id
.venv/bin/python -m trading_system.cli fetch-idx-broker-flow --start 2026-01-01
```

### 4. Update corporate actions & adjusted close

```bash
.venv/bin/python -m trading_system.cli corporate-actions
.venv/bin/python -m trading_system.cli update-adjusted-close
```

### 5. Compute scores for all tickers

```bash
# Single ticker
.venv/bin/python -m trading_system.cli compute-scores BBCA.JK

# All tickers (long running)
.venv/bin/python -m trading_system.cli compute-scores --all
```

### 6. Sync to Parquet

```bash
.venv/bin/python scripts/sync_parquet_flashdisk.py
```

### 7. Verify data freshness

```bash
curl -s -H "X-API-Key: dev-secret-key-2026" http://localhost:8000/api/data-overview | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f'Tickers: {d[\"tickers\"][\"total\"]} total, {d[\"tickers\"][\"active\"]} active')
print(f'Date range: {d[\"date_range\"][\"first\"]} to {d[\"date_range\"][\"last\"]}')
print(f'Stale tickers: {len(d[\"stale_tickers\"])}')
"
```

### 8. Run daily runner (all-in-one)

```bash
# Full pipeline: fetch + compute + render + notify
.venv/bin/python -m trading_system.cli schedule

# Or once mode (no loop)
.venv/bin/python -m trading_system.cli schedule --once
```
