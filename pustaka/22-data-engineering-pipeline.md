# Data Engineering & Pipeline untuk Sistem Trading

> **Tujuan:** Dokumen ini adalah referensi definitif untuk arsitektur data engineering sistem trading — dari ingestion, ETL, storage, real-time feeds, data quality, hingga governance — dengan fokus pada pasar modal Indonesia (IDX).

---

## Daftar Isi

1. [Arsitektur Data Pipeline](#1-arsitektur-data-pipeline)
2. [Data Sources & Ingestion](#2-data-sources--ingestion)
3. [Storage Architecture](#3-storage-architecture)
4. [ETL vs ELT](#4-etl-vs-elt)
5. [Real-Time Data Feeds](#5-real-time-data-feeds)
6. [Data Quality Framework](#6-data-quality-framework)
7. [Data Normalization & Standardization](#7-data-normalization--standardization)
8. [Time Series Database](#8-time-series-database)
9. [Data Lineage & Governance](#9-data-lineage--governance)
10. [Parquet & Cold Storage](#10-parquet--cold-storage)
11. [Implementasi untuk IDX](#11-implementasi-untuk-idx)
12. [Checklist Implementasi](#12-checklist-implementasi)

---

## 1. Arsitektur Data Pipeline

### 1.1 Layer Arsitektur

```
┌─────────────────────────────────────────────────────────────────────┐
│                     DATA SOURCES                                    │
│  Yahoo Finance │ IDX Scraper │ RSS │ Reddit │ BPS/BI │ FRED        │
└──────────┬──────────┬──────────┬──────────┬──────────┬──────────────┘
           │          │          │          │          │
     ┌─────▼──────────▼──────────▼──────────▼──────────▼─────┐
     │              INGESTION LAYER                           │
     │  Rate Limiter │ Auth │ Retry │ Circuit Breaker         │
     └─────┬──────────────────────────────────────────────────┘
           │
     ┌─────▼──────────────────────────────────────────────────┐
     │              VALIDATION LAYER                          │
     │  Schema │ Range │ Completeness │ Freshness │ Outlier   │
     └─────┬──────────────────────────────────────────────────┘
           │
     ┌─────▼──────────────────────────────────────────────────┐
     │              TRANSFORMATION LAYER                      │
     │  Normalize │ Enrich │ Aggregate │ Corporate Actions    │
     └─────┬──────────────────────────────────────────────────┘
           │
     ┌─────▼──────────────────────────────────────────────────┐
     │              STORAGE LAYER                             │
     │  SQLite (hot) │ Parquet (cold) │ Redis (cache)         │
     └─────┬──────────────────────────────────────────────────┘
           │
     ┌─────▼──────────────────────────────────────────────────┐
     │              SERVING LAYER                             │
     │  API │ WebSocket │ Analysis Engines │ Decision Engine  │
     └────────────────────────────────────────────────────────┘
```

### 1.2 Prinsip Desain

| Prinsip | Deskripsi | Dampak jika Dilanggar |
|---------|-----------|----------------------|
| **Single Source of Truth** | Satu sumber data otoritatif per data type | Inkonsistensi antar engine |
| **Schema on Write** | Validasi schema saat ingest, bukan saat read | Data corrupt tidak terdeteksi |
| **Idempotent Ingestion** | Re-run ingestion tidak duplikasi data | Duplikat, double counting |
| **Fail-Fast** | Error di ingest → stop, jangan lanjut | Data buruk masuk pipeline |
| **Audit Trail** | Setiap batch ingest tercatat | Tidak traceable |
| **Backfill Capability** | Bisa re-ingest data historis | Gap data permanen |

---

## 2. Data Sources & Ingestion

### 2.1 Sumber Data untuk IDX

| Sumber | Data | Frekuensi | Rate Limit | Kualitas |
|--------|------|-----------|------------|----------|
| **Yahoo Finance** | OHLCV, split, dividend | Daily (EOD) | 1 req/sec | Medium (delayed) |
| **IDX.co.id** | Foreign flow, broker flow, announcement | Daily | 0.3 req/sec | High (official) |
| **RSS Feeds** | News, corporate actions | Real-time | N/A | Medium |
| **BPS (Badan Pusat Statistik)** | Macro data (GDP, inflation, trade) | Monthly/Quarterly | N/A | High |
| **Bank Indonesia** | BI rate, exchange rate, money supply | Daily/Monthly | N/A | High |
| **FRED** | Global macro (US rates, commodities) | Daily | 120 req/min | High |
| **Reddit/X** | Social sentiment | Real-time | API limits | Low (noisy) |
| **Google Trends** | Search interest | Weekly | 1 req/sec | Low (indicative) |

> **Catatan:** Yahoo Finance memiliki **10 menit delay** untuk data IDX (.JK), vs real-time untuk US market. Untuk detail lengkap delay per provider, overlap zona waktu global, dan strategi mitigasi overnight gap, lihat **`36-gap-data-timezone-global-idx.md`**.

### 2.2 Ingestion Pattern

```python
class DataIngestor:
    """Generic data ingestion with rate limiting and retry."""
    
    def __init__(self, rate_limiter, storage, source_name):
        self.rate_limiter = rate_limiter
        self.storage = storage
        self.source_name = source_name
        self.max_retries = 3
        self.retry_delay = 5  # seconds
    
    def ingest(self, ticker: str, start_date, end_date):
        """Ingest data with retry and validation."""
        for attempt in range(self.max_retries):
            try:
                self.rate_limiter.acquire()
                raw_data = self._fetch(ticker, start_date, end_date)
                
                if raw_data is None or raw_data.empty:
                    self.storage.record_source_health(
                        self.source_name, "warning", "No data returned"
                    )
                    return None
                
                # Validate
                validated = self._validate(raw_data, ticker)
                if validated.empty:
                    return None
                
                # Normalize
                normalized = self._normalize(validated)
                
                # Store
                rows = self.storage.save_ohlcv(ticker, normalized)
                
                # Audit
                self.storage.audit("data.ingest", {
                    "source": self.source_name,
                    "ticker": ticker,
                    "rows": rows,
                    "date_range": f"{start_date} to {end_date}",
                })
                
                return rows
                
            except Exception as e:
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                else:
                    self.storage.record_source_health(
                        self.source_name, "error", str(e)
                    )
                    raise
```

### 2.3 Rate Limiting

```python
class RateLimiter:
    """Token bucket rate limiter."""
    
    def __init__(self, calls_per_second: float):
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0.0
    
    def acquire(self):
        """Block until rate limit allows next call."""
        now = time.time()
        elapsed = now - self.last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_call = time.time()
```

| Source | Rate Limit | Implementasi |
|--------|-----------|--------------|
| Yahoo Finance | 1 req/sec | `RateLimiter(1.0)` |
| IDX.co.id | ~3 req/sec (0.3s/req) | `RateLimiter(3.0)` |
| FRED | 120 req/min | `RateLimiter(2.0)` |
| Google Trends | 1 req/sec | `RateLimiter(1.0)` |

---

## 3. Storage Architecture

### 3.1 Hot vs Cold Storage

| Tier | Technology | Data | Retention | Query Latency |
|------|-----------|------|-----------|---------------|
| **Hot** | SQLite (WAL mode) | Recent data, scores, positions | 90 days | < 10ms |
| **Warm** | SQLite (indexed) | Historical OHLCV, indicators | All | < 100ms |
| **Cold** | Parquet (columnar) | Raw archive, snapshots | Forever | Seconds |
| **Cache** | Redis (optional) | Frequent queries, session | TTL | < 1ms |

### 3.2 SQLite Configuration

```python
# WAL mode for concurrent read/write
conn = sqlite3.connect(db_path)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")  # Balance safety/speed
conn.execute("PRAGMA cache_size=-64000")   # 64MB cache
conn.execute("PRAGMA temp_store=MEMORY")
conn.execute("PRAGMA mmap_size=268435456")  # 256MB memory-mapped
```

### 3.3 Index Strategy

```sql
-- Critical indexes for trading system
CREATE INDEX IF NOT EXISTS idx_ohlcv_ticker_date ON ohlcv(ticker, date DESC);
CREATE INDEX IF NOT EXISTS idx_scores_ticker_engine_date ON scores(ticker, engine, date DESC);
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status, ticker);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_event_timestamp ON audit_log(event, timestamp DESC);
```

### 3.4 Partitioning Strategy (for larger DBs)

| Table | Partition Key | Strategy |
|-------|--------------|----------|
| `ohlcv` | `date` | Yearly partitions |
| `orders` | `created_at` | Monthly partitions |
| `audit_log` | `timestamp` | Monthly partitions |
| `scores` | `date` | Monthly partitions |

> **Catatan:** SQLite tidak mendukung native partitioning. Untuk skala besar, migrasi ke PostgreSQL/TimescaleDB.

---

## 4. ETL vs ELT

### 4.1 Perbandingan

| Aspek | ETL | ELT |
|-------|-----|-----|
| **Transform timing** | Before load | After load |
| **Best for** | Limited compute at target | Powerful target DB |
| **Data quality** | Early detection | Late detection |
| **Complexity** | Higher (transform engine) | Lower (SQL transforms) |
| **Trading system** | ✅ Preferred | Less suitable |

### 4.2 ETL Pipeline untuk Trading

```python
def etl_pipeline(ticker: str, date_range):
    """Extract → Transform → Load pipeline."""
    
    # EXTRACT: Fetch raw data
    raw = fetch_from_yahoo(ticker, date_range)
    if raw.empty:
        raise DataError(f"No data for {ticker}")
    
    # TRANSFORM: Validate, normalize, enrich
    validated = validate_schema(raw, OHLCV_SCHEMA)
    cleaned = handle_missing_values(validated)
    normalized = normalize_timestamps(cleaned, timezone="Asia/Jakarta")
    enriched = add_derived_columns(normalized)  # returns, log_returns, ATR
    
    # LOAD: Persist to storage
    rows = storage.save_ohlcv(ticker, enriched)
    
    # Post-load: Update source health
    storage.record_source_health("yahoo_finance", "ok", f"{rows} rows")
    
    return {"ticker": ticker, "rows": rows, "status": "ok"}
```

### 4.3 Batch vs Streaming

| Mode | Use Case | Latency | Complexity |
|------|----------|---------|------------|
| **Batch (EOD)** | Historical data, daily scores | Hours | Low |
| **Micro-batch** | Intraday data, 5-min bars | Minutes | Medium |
| **Streaming** | Real-time ticks, order book | Seconds | High |

> **Untuk IDX retail/individual:** Batch EOD sudah cukup. Real-time hanya untuk monitoring.

---

## 5. Real-Time Data Feeds

### 5.1 WebSocket Architecture

```python
import asyncio
import websockets
import json

class RealTimeFeed:
    """WebSocket-based real-time data feed."""
    
    def __init__(self, url, on_message callback):
        self.url = url
        self.on_message = callback
        self.reconnect_delay = 1
        self.max_reconnect_delay = 60
    
    async def connect(self):
        """Connect with exponential backoff."""
        while True:
            try:
                async with websockets.connect(self.url) as ws:
                    self.reconnect_delay = 1  # reset
                    async for message in ws:
                        data = json.loads(message)
                        await self.on_message(data)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(
                    self.reconnect_delay * 2, 
                    self.max_reconnect_delay
                )
```

### 5.2 Feed Handler Pattern

```
Exchange/Broker API
       │
       ▼
┌──────────────┐
│ Feed Handler │  ← Decode protocol (FIX/JSON/proprietary)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Normalizer   │  ← Convert to internal format
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Validator    │  ← Check sequence, gaps, outliers
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ Distributor  │  ← Fan-out to consumers (pub/sub)
└──────────────┘
```

### 5.3 Sequence Number Validation

```python
def validate_sequence(messages: list, expected_seq: int):
    """Validate message sequence numbers."""
    gaps = []
    for msg in messages:
        seq = msg.get("sequence")
        if seq != expected_seq:
            gaps.append({"expected": expected_seq, "got": seq})
            # Trigger gap recovery
        expected_seq = seq + 1
    return gaps
```

---

## 6. Data Quality Framework

### 6.1 Dimension of Data Quality

| Dimension | Deskripsi | Check | Threshold |
|-----------|-----------|-------|-----------|
| **Completeness** | Tidak ada missing values | Null count per column | < 1% |
| **Accuracy** | Nilai sesuai realitas | Cross-source validation | 99% match |
| **Consistency** | Format sama across sources | Schema validation | 100% |
| **Timeliness** | Data up-to-date | Freshness check | < 24h (EOD) |
| **Uniqueness** | Tidak ada duplikasi | Primary key check | 0 duplicates |
| **Validity** | Dalam range yang masuk akal | Range check | 0 violations |

### 6.2 Validation Rules

```python
OHLCV_SCHEMA = {
    "ticker": {"type": "str", "required": True},
    "date": {"type": "datetime", "required": True},
    "open": {"type": "float", "min": 0, "max": 1e8},
    "high": {"type": "float", "min": 0, "max": 1e8},
    "low": {"type": "float", "min": 0, "max": 1e8},
    "close": {"type": "float", "min": 0, "max": 1e8},
    "volume": {"type": "int", "min": 0},
}

VALIDATION_RULES = {
    "high_ge_low": lambda df: (df["high"] >= df["low"]).all(),
    "high_ge_open": lambda df: (df["high"] >= df["open"]).all(),
    "high_ge_close": lambda df: (df["high"] >= df["close"]).all(),
    "low_le_open": lambda df: (df["low"] <= df["open"]).all(),
    "low_le_close": lambda df: (df["low"] <= df["close"]).all(),
    "volume_positive": lambda df: (df["volume"] >= 0).all(),
    "no_duplicates": lambda df: not df.duplicated(subset=["ticker", "date"]).any(),
    "price_change_limit": lambda df: (
        (df.groupby("ticker")["close"].pct_change().abs() < 0.20)
    ).all(),  # IDX auto-reject ±15-20%
}

def validate_ohlcv(df: pd.DataFrame) -> tuple[bool, list]:
    """Validate OHLCV data against rules."""
    errors = []
    for rule_name, rule_fn in VALIDATION_RULES.items():
        try:
            if not rule_fn(df):
                errors.append(f"Rule violated: {rule_name}")
        except Exception as e:
            errors.append(f"Rule error ({rule_name}): {e}")
    return len(errors) == 0, errors
```

### 6.3 Data Quality Score

```python
def compute_quality_score(df: pd.DataFrame) -> float:
    """Compute data quality score (0-100)."""
    checks = {
        "completeness": 1 - (df.isnull().sum().sum() / df.size),
        "uniqueness": 1 - (df.duplicated().sum() / len(df)),
        "validity": sum(1 for r in VALIDATION_RULES.values() if r(df)) / len(VALIDATION_RULES),
    }
    return sum(checks.values()) / len(checks) * 100
```

### 6.4 Anomaly Detection

```python
def detect_anomalies(df: pd.DataFrame, ticker: str) -> list:
    """Detect price/volume anomalies."""
    anomalies = []
    
    # Price jump > 3 standard deviations
    returns = df["close"].pct_change()
    z_score = (returns - returns.mean()) / returns.std()
    outliers = df[abs(z_score) > 3]
    
    for idx, row in outliers.iterrows():
        anomalies.append({
            "type": "price_jump",
            "ticker": ticker,
            "date": row["date"],
            "change_pct": returns.loc[idx],
            "z_score": z_score.loc[idx],
        })
    
    # Volume spike > 5x average
    vol_avg = df["volume"].rolling(20).mean()
    vol_spike = df[df["volume"] > 5 * vol_avg]
    
    for idx, row in vol_spike.iterrows():
        anomalies.append({
            "type": "volume_spike",
            "ticker": ticker,
            "date": row["date"],
            "volume": row["volume"],
            "avg_volume": vol_avg.loc[idx],
        })
    
    return anomalies
```

---

## 7. Data Normalization & Standardization

### 7.1 Timestamp Normalization

```python
def normalize_timestamps(df: pd.DataFrame, tz: str = "Asia/Jakarta"):
    """Normalize timestamps to consistent timezone."""
    df["date"] = pd.to_datetime(df["date"], format="mixed", utc=True)
    df["date"] = df["date"].dt.tz_convert(tz)
    return df
```

### 7.2 Corporate Action Adjustment

```python
def adjust_for_splits(df: pd.DataFrame, splits: pd.DataFrame) -> pd.DataFrame:
    """Adjust OHLCV for stock splits."""
    df = df.copy()
    for _, split in splits.iterrows():
        mask = df["date"] < split["ex_date"]
        ratio = split["ratio"]  # e.g., 2 for 1:2 split
        df.loc[mask, ["open", "high", "low", "close"]] /= ratio
        df.loc[mask, "volume"] *= ratio
    return df
```

### 7.3 Currency Normalization

```python
def normalize_currency(df: pd.DataFrame, target: str = "IDR"):
    """Normalize all monetary values to target currency."""
    if "currency" not in df.columns:
        df["currency"] = "IDR"  # default for IDX
    
    for currency in df["currency"].unique():
        if currency != target:
            rate = get_fx_rate(currency, target)
            mask = df["currency"] == currency
            price_cols = ["open", "high", "low", "close"]
            df.loc[mask, price_cols] *= rate
            df.loc[mask, "currency"] = target
    
    return df
```

---

## 8. Time Series Database

### 8.1 SQLite vs TimescaleDB vs InfluxDB

| Aspect | SQLite | TimescaleDB | InfluxDB |
|--------|--------|-------------|----------|
| **Type** | Embedded | PostgreSQL ext | Purpose-built TS |
| **Scale** | ~500GB | Terabytes | Terabytes |
| **Write throughput** | ~10K rows/s | ~100K rows/s | ~1M rows/s |
| **Query** | SQL | SQL | InfluxQL/Flux |
| **Retention** | Manual | Auto-hypertable | Auto-downsample |
| **Complexity** | Low | Medium | Medium |
| **Best for** | < 10M rows | Medium-large | Large-scale IoT |

### 8.2 Migration Path

```
SQLite (current) → PostgreSQL + TimescaleDB (growth) → kdb+ (HFT)
```

### 8.3 TimescaleDB Schema (Future)

```sql
-- Hypertable for OHLCV
CREATE TABLE ohlcv_ts (
    ticker TEXT NOT NULL,
    date TIMESTAMPTZ NOT NULL,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    volume BIGINT,
    PRIMARY KEY (ticker, date)
);

SELECT create_hypertable('ohlcv_ts', 'date', chunk_time_interval => INTERVAL '1 year');

-- Continuous aggregates for daily/weekly/monthly
CREATE MATERIALIZED VIEW ohlcv_daily
WITH (timescaledb.continuous) AS
SELECT ticker, date_trunc('day', date) AS day,
       first(open, date) AS open, max(high) AS high,
       min(low) AS low, last(close, date) AS close,
       sum(volume) AS volume
FROM ohlcv_ts GROUP BY ticker, day;

-- Retention policy
SELECT add_retention_policy('ohlcv_ts', INTERVAL '10 years');
```

---

## 9. Data Lineage & Governance

### 9.1 Data Lineage

```python
def record_lineage(storage, source, dataset, transformation, inputs, outputs):
    """Record data lineage for audit."""
    storage.audit("data.lineage", {
        "source": source,
        "dataset": dataset,
        "transformation": transformation,
        "inputs": inputs,
        "outputs": outputs,
        "timestamp": datetime.now(UTC).isoformat(),
    })
```

### 9.2 Data Catalog

| Dataset | Source | Owner | Freshness | Quality | Schema |
|---------|--------|-------|-----------|---------|--------|
| `ohlcv` | Yahoo Finance | Data Engine | Daily EOD | 98% | OHLCV schema |
| `foreign_flow` | IDX.co.id | Data Engine | Daily EOD | 95% | Flow schema |
| `macro_data` | BPS/BI/FRED | Data Engine | Monthly | 100% | Macro schema |
| `scores` | Analysis engines | Analysis Engine | On-demand | N/A | Score schema |
| `news` | RSS feeds | Sentiment Engine | Real-time | 80% | News schema |

### 9.3 Data Retention Policy

| Data Type | Hot Storage | Cold Storage | Archive |
|-----------|------------|-------------|---------|
| OHLCV | 5 years (SQLite) | 10 years (Parquet) | Forever (compressed) |
| Orders | 1 year | 7 years | 7 years (regulatory) |
| Audit log | 90 days | 7 years | 7 years (regulatory) |
| Scores | 1 year | 3 years | 5 years |
| News | 30 days | 1 year | 3 years |

---

## 10. Parquet & Cold Storage

### 10.1 Parquet Benefits

| Feature | Parquet | CSV | JSON |
|---------|---------|-----|------|
| Columnar | ✅ | ❌ | ❌ |
| Compression | Snappy/Zstd | None | None |
| Schema | Embedded | External | External |
| Query (column subset) | Fast | Slow | Slow |
| Size (typical) | 10x smaller | Baseline | 2x larger |

### 10.2 Parquet Organization

```
/data/trading_data/
├── raw/                    # Raw ingested data
│   ├── ohlcv/
│   │   ├── BBCA.JK.parquet
│   │   ├── TLKM.JK.parquet
│   │   └── ...
│   ├── foreign_flow/
│   ├── macro/
│   └── news/
├── archive/                # Processed/archived
│   ├── tables/
│   │   ├── ohlcv_2024.parquet
│   │   ├── ohlcv_2025.parquet
│   │   └── ...
│   └── snapshots/
└── exports/                # Analysis exports
```

### 10.3 Parquet Read/Write

```python
import pyarrow as pa
import pyarrow.parquet as pq

def save_parquet(df: pd.DataFrame, path: str, compression: str = "snappy"):
    """Save DataFrame to Parquet."""
    table = pa.Table.from_pandas(df)
    pq.write_table(table, path, compression=compression)

def load_parquet(path: str, columns: list = None, filters = None):
    """Load Parquet with column pruning and row filtering."""
    table = pq.read_table(path, columns=columns, filters=filters)
    return table.to_pandas()
```

---

## 11. Implementasi untuk IDX

### 11.1 Pertimbangan Khusus

| Faktor | Implikasi | Solusi |
|--------|-----------|--------|
| **EOD data only** (Yahoo) | Tidak ada intraday gratis | Batch EOD pipeline |
| **IDX scraper fragile** | HTML structure berubah | Monitor + alert on parse errors |
| **Timezone WIB** | UTC+7, no DST | Normalize to Asia/Jakarta |
| **Auto-reject ±15-20%** | Price validation | Include in validation rules |
| **Suspend/delisting** | Saham hilang | is_active flag, filter downstream |
| **Corporate actions frequent** | Price adjustment | Automated CA adjustment |
| **951 tickers aktif** | Batch ingestion lambat | Parallel ingestion (throttled) |

### 11.2 Batch Ingestion Schedule

```python
SCHEDULE = {
    "06:00": "fetch_ohlcv_all",         # Pre-market data update
    "06:30": "fetch_idx_foreign_flow",   # IDX foreign flow
    "07:00": "fetch_idx_broker_flow",    # IDX broker flow
    "07:30": "fetch_macro_data",         # Macro updates
    "08:00": "fetch_news_rss",           # Morning news
    "12:00": "fetch_news_rss",           # Midday news
    "16:30": "fetch_ohlcv_all",          # Post-market EOD
    "17:00": "compute_scores_all",       # Score computation
    "18:00": "archive_to_parquet",       # Cold archive
}
```

### 11.3 Data Gap Handling

```python
def detect_data_gaps(df: pd.DataFrame, ticker: str, expected_freq: str = "D"):
    """Detect missing trading days."""
    df = df.sort_values("date")
    df["date"] = pd.to_datetime(df["date"])
    
    # Generate expected business days (exclude weekends + holidays)
    date_range = pd.bdate_range(
        start=df["date"].min(),
        end=df["date"].max(),
        freq="B",  # Business days
    )
    
    # Remove known holidays from market_calendar
    holidays = get_market_holidays()
    expected_dates = date_range.drop(holidays)
    
    actual_dates = pd.DatetimeIndex(df["date"].dt.date)
    missing = expected_dates.difference(actual_dates)
    
    if len(missing) > 0:
        logger.warning(f"{ticker}: {len(missing)} missing trading days")
        return list(missing)
    return []
```

---

## 12. Checklist Implementasi

### Ingestion
- [ ] Yahoo Finance fetcher with rate limiting
- [ ] IDX scraper (foreign flow, broker flow)
- [ ] RSS feed fetcher (news)
- [ ] Macro data fetcher (BPS, BI, FRED)
- [ ] Retry with exponential backoff
- [ ] Circuit breaker for source failures
- [ ] Source health monitoring

### Validation
- [ ] Schema validation (column types, required fields)
- [ ] Range validation (price > 0, high ≥ low, etc.)
- [ ] Completeness check (null percentage)
- [ ] Duplicate detection (ticker + date)
- [ ] Anomaly detection (price jump, volume spike)
- [ ] Data quality score computation

### Storage
- [ ] SQLite with WAL mode
- [ ] Proper indexes on hot queries
- [ ] Parquet cold archive
- [ ] Data retention policy
- [ ] Backup strategy (daily snapshot)

### Pipeline
- [ ] Batch EOD ingestion scheduler
- [ ] Idempotent ingestion (no duplicates on re-run)
- [ ] Data gap detection
- [ ] Corporate action adjustment
- [ ] Timestamp normalization (Asia/Jakarta)
- [ ] Audit trail for every batch

### Quality
- [ ] Automated quality score per dataset
- [ ] Alert on quality degradation
- [ ] Cross-source validation (when available)
- [ ] Freshness monitor (data < 24h old)
- [ ] Lineage tracking

### Future-Proofing
- [ ] Migration plan to PostgreSQL/TimescaleDB
- [ ] Schema versioning (Alembic migrations)
- [ ] API for data access (abstract storage details)
- [ ] Parallel ingestion support

---

## Referensi

1. `src/trading_system/data/acquisition.py` — Yahoo Finance fetcher
2. `src/trading_system/data/storage.py` — SQLite storage layer
3. `src/trading_system/data/validation.py` — Data validation
4. `src/trading_system/data/idx_scraper.py` — IDX scraper
5. `src/trading_system/data/rate_limiter.py` — Rate limiting
6. `pustaka/18-modul-engine-data-wajib.md` — Module & data registry
7. `pustaka/19-flow-logic-testing-kpi.md` — Data flow end-to-end
8. TimescaleDB Documentation: https://docs.timescale.com
9. Apache Parquet Documentation: https://parquet.apache.org
10. "Designing Data-Intensive Applications" — Martin Kleppmann

---

> **Catatan:** Data engineering adalah fondasi sistem trading. Data buruk → analisis buruk → keputusan buruk → kerugian. Investasi waktu terbesar harus di pipeline data.
