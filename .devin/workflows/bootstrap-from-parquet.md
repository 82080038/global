# Workflow: Bootstrap Database from Parquet

## Purpose
Rebuild the SQLite database from Parquet archive files. Use when database is corrupted, missing, or needs fresh load.

## Prerequisites

- Parquet files in `/media/petrick/Parquet/trading_data/raw/` and `/archive/`
- `.venv/` virtualenv with all dependencies installed
- `.env` configured with correct paths

## Steps

### 1. Backup current database (if exists)

```bash
cp data/trading_system.db data/trading_system.db.bak.$(date +%Y%m%d)
```

### 2. Remove current database

```bash
rm -f data/trading_system.db data/trading_system.db-wal data/trading_system.db-shm
```

### 3. Run Alembic migrations to create schema

```bash
.venv/bin/alembic upgrade head
```

### 4. Bootstrap from Parquet archive

```bash
.venv/bin/python scripts/bootstrap_from_parquet.py
```

This loads:
- ~995 raw parquet files → OHLCV data
- ~28 archive table files → all other tables
- ~991 tickers into instrument_master

### 5. Verify data loaded

```bash
.venv/bin/python -c "
from trading_system.data.storage import DataStorage
s = DataStorage()
with s._connect() as conn:
    tables = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name\").fetchall()
    print(f'Total tables: {len(tables)}')
    for t in tables:
        cnt = conn.execute(f'SELECT COUNT(*) FROM {t[0]}').fetchone()[0]
        if cnt > 0:
            print(f'  {t[0]}: {cnt:,} rows')
"
```

### 6. Verify instrument classification

```bash
.venv/bin/python -c "
from trading_system.data.storage import DataStorage
s = DataStorage()
with s._connect() as conn:
    rows = conn.execute('''
        SELECT asset_class, is_active, COUNT(*) as cnt
        FROM instrument_master
        GROUP BY asset_class, is_active
        ORDER BY asset_class, is_active
    ''').fetchall()
    for r in rows:
        status = 'active' if r[1] else 'delisted'
        print(f'  {r[0]:15s} {status:10s} {r[2]} tickers')
"
```

### 7. Start servers and verify

```bash
# Start API
ENV=development API_KEY=dev-secret-key-2026 .venv/bin/uvicorn trading_system.api.app:app --port 8000 --log-level warning &

# Verify
curl -s -H "X-API-Key: dev-secret-key-2026" http://localhost:8000/api/data-overview | python3 -m json.tool | head -20
```

### Notes

- `policy_events` parquet has Indonesian column names — `bootstrap_from_parquet.py` maps them automatically.
- `normalize_ohlcv` uses `format="mixed", utc=True` for `ingested_at` due to mixed datetime formats.
- 3 tickers (EURIDR=X, IDR=X, JPYIDR=X) may be skipped if quality=0.0 — this is expected for forex without OHLCV.
