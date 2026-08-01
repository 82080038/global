# Database Conventions

- **Engine**: SQLite in WAL mode
- **Path**: `data/trading_system.db`
- **Migrations**: Alembic (`alembic/versions/`)
- **Current migrations**: `0001_initial.py`, `0002_d1_d31_tables.py`

## Guidelines

- Always use Alembic for schema changes — never modify the schema manually.
- Create a new migration file in `alembic/versions/` with a descriptive filename.
- Use SQLAlchemy ORM models; avoid raw SQL unless performance-critical.
- Default tickers: `BBCA.JK`, `TLKM.JK`, `ASII.JK`, `UNVR.JK`, `BMRI.JK`.
- Query the database for current row counts; do not rely on hardcoded snapshots.
