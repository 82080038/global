# Database Conventions

- **Engine**: SQLite in WAL mode
- **Path**: `data/trading_system.db` (~460 MB)
- **Migrations**: Alembic (`alembic/versions/`)
- **Current migrations**: `0001_initial.py`, `0002_d1_d31_tables.py`, `0003_ipo_suspension_delisting.py`
- **Total tables**: 41 (query DB for current count — do not hardcode)

## Key Tables

| Table | Purpose |
|-------|---------|
| `ohlcv` | Historical price data (open/high/low/close/volume) |
| `technical_indicators` | RSI, MACD, MA, Bollinger Bands |
| `fundamental_data` | Financial statements, ratios |
| `macro_data` | Interest rates, inflation, GDP, IHSG |
| `foreign_flow` | Foreign net buy/sell per ticker |
| `broker_flow` | Broker-level transaction summary |
| `instrument_master` | Ticker metadata (active/delisted, asset_class) |
| `scores` | Multi-factor decision scores |
| `render_log` | Render tracking per table/ticker |
| `data_watermark` | Fetch tracking & freshness |
| `market_calendar` | Trading days, holidays, half-days |

## Instrument Classification

- **Equity stocks (saham)**: `asset_class = 'equity'` — 928 active, 40 delisted
- **Non-equity reference**: forex (4), index (12), commodity (4), ETF (4) — used as macro/global reference, NOT for trading signals
- **Downstream engines** must filter `is_active = 1 AND asset_class = 'equity'` to process only listed saham

## Parquet Storage

- **Raw dir**: `DATA_RAW_DIR` env var (default: `/media/petrick/Parquet/trading_data/raw`) — ~1222 files, ~162 MB
- **Archive dir**: `DATA_ARCHIVE_DIR` env var (default: `/media/petrick/Parquet/trading_data/archive`) — ~1027 files, ~106 MB
- **Sync status**: Check via `/api/storage-info` endpoint

## Guidelines

- Always use Alembic for schema changes — never modify the schema manually.
- Create a new migration file in `alembic/versions/` with format `NNNN_descriptive_name.py`.
- Use SQLAlchemy ORM models; avoid raw SQL unless performance-critical.
- Query the database for current row counts; do not rely on hardcoded snapshots.
- When adding tickers, set `asset_class` correctly (`equity` for stocks, `forex`/`index`/`commodity`/`etf` for reference data).
- Render log: use `storage.log_render()` after rendering data to track freshness.
