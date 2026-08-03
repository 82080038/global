"""Add IPO data, trading suspensions, and instrument status tracking.

Adds columns to instrument_master for IPO metadata and lifecycle status,
and creates a trading_suspensions table to track temporary trading halts.

This enables:
- Survivorship bias prevention in backtests (filter by listing/delisting date)
- No-trade logic for suspended/delisted/IPO lock-up periods
- ML labeling that skips non-tradeable periods

Revision ID: 0003_ipo_suspend
Revises: 0002_d1_d31
Create Date: 2026-08-04

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_ipo_suspend"
down_revision: Union[str, None] = "0002_d1_d31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add IPO fields, status column to instrument_master; create trading_suspensions."""

    # Add IPO and lifecycle columns to instrument_master
    # SQLite doesn't support ADD COLUMN IF NOT EXISTS, so we check pragma first.
    conn = op.get_bind()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(instrument_master)").fetchall()}

    if "ipo_date" not in cols:
        op.execute("ALTER TABLE instrument_master ADD COLUMN ipo_date TEXT")
    if "ipo_price" not in cols:
        op.execute("ALTER TABLE instrument_master ADD COLUMN ipo_price REAL")
    if "status" not in cols:
        op.execute("ALTER TABLE instrument_master ADD COLUMN status TEXT DEFAULT 'active'")
    if "lock_up_end_date" not in cols:
        op.execute("ALTER TABLE instrument_master ADD COLUMN lock_up_end_date TEXT")

    # Backfill status from is_active for existing rows
    op.execute("""
        UPDATE instrument_master
        SET status = CASE
            WHEN is_active = 0 OR is_active IS NULL THEN 'delisted'
            ELSE 'active'
        END
        WHERE status IS NULL OR status = ''
    """)

    # Create trading_suspensions table
    op.execute("""
        CREATE TABLE IF NOT EXISTS trading_suspensions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            suspend_date TEXT NOT NULL,
            resume_date TEXT,
            reason TEXT,
            suspension_type TEXT,
            source TEXT,
            created_at TEXT NOT NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_suspension_ticker ON trading_suspensions(ticker)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_suspension_date ON trading_suspensions(suspend_date)")


def downgrade() -> None:
    """Remove IPO fields, status column; drop trading_suspensions."""
    op.execute("DROP TABLE IF EXISTS trading_suspensions")
    op.execute("DROP INDEX IF EXISTS idx_suspension_ticker")
    op.execute("DROP INDEX IF EXISTS idx_suspension_date")

    # SQLite doesn't support DROP COLUMN before 3.35; recreate without new columns
    conn = op.get_bind()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(instrument_master)").fetchall()}
    new_cols = {"ipo_date", "ipo_price", "status", "lock_up_end_date"}
    if new_cols & cols:
        op.execute("""
            CREATE TABLE _instrument_master_old AS
            SELECT ticker, name, sector, subsector, exchange, listing_date,
                   delisting_date, is_active, board, market_cap, free_float,
                   asset_class, updated_at
            FROM instrument_master
        """)
        op.execute("DROP TABLE instrument_master")
        op.execute("""
            CREATE TABLE instrument_master (
                ticker TEXT PRIMARY KEY, name TEXT, sector TEXT, subsector TEXT,
                exchange TEXT, listing_date TEXT, delisting_date TEXT,
                is_active INTEGER DEFAULT 1, board TEXT, market_cap REAL,
                free_float REAL, asset_class TEXT DEFAULT 'equity', updated_at TEXT
            )
        """)
        op.execute("INSERT INTO instrument_master SELECT * FROM _instrument_master_old")
        op.execute("DROP TABLE _instrument_master_old")
