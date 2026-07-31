"""Initial schema — create all tables from SCHEMA definition.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-31

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables from the application's SCHEMA definition."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

    from trading_system.data.storage import SCHEMA

    op.execute("PRAGMA foreign_keys=ON")
    op.executescript(SCHEMA)


def downgrade() -> None:
    """Drop all tables."""
    op.execute("PRAGMA foreign_keys=OFF")
    tables = [
        "daily_risk_metrics",
        "ai_weights",
        "watchlist",
        "equity_snapshots",
        "orders",
        "positions",
        "news",
        "corporate_actions",
        "relationship_matrix",
        "scores",
        "audit_log",
        "source_health",
        "ohlcv",
    ]
    for table in tables:
        op.execute(f"DROP TABLE IF EXISTS {table}")
