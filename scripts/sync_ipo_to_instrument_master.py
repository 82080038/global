"""Sync IPO data from legacy stock_ipo table to instrument_master fields.

Copies ipo_date and ipo_price from the legacy `stock_ipo` table (imported from
the old pasar_modal system) into the new `instrument_master` columns
(ipo_date, ipo_price) that were added in migration 0003.

Also syncs listing_date from mm_listing if available.

Usage:
    python -m scripts.sync_ipo_to_instrument_master [--dry-run]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "trading_system.db"


def sync_ipo_data(db_path: Path, dry_run: bool = False) -> dict:
    """Copy IPO data from stock_ipo → instrument_master.

    Returns dict with counts: {updated, skipped, not_found, total_legacy}.
    """
    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        return {"updated": 0, "skipped": 0, "not_found": 0, "total_legacy": 0}

    conn = sqlite3.connect(str(db_path))

    # Check if stock_ipo table exists
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='stock_ipo'"
    )
    if not cur.fetchone():
        print("Table 'stock_ipo' not found — nothing to sync.")
        conn.close()
        return {"updated": 0, "skipped": 0, "not_found": 0, "total_legacy": 0}

    # Check if instrument_master has ipo_date column
    cols = {r[1] for r in conn.execute("PRAGMA table_info(instrument_master)").fetchall()}
    if "ipo_date" not in cols:
        print("ERROR: instrument_master does not have ipo_date column. Run migration 0003 first.")
        conn.close()
        return {"updated": 0, "skipped": 0, "not_found": 0, "total_legacy": 0}

    # Load all stock_ipo records
    rows = conn.execute(
        "SELECT kode, ipo_date, ipo_price FROM stock_ipo WHERE kode IS NOT NULL"
    ).fetchall()

    total_legacy = len(rows)
    updated = 0
    skipped = 0
    not_found = 0

    for kode, ipo_date, ipo_price in rows:
        # Try matching with .JK suffix
        ticker_candidates = [kode, f"{kode}.JK"] if not kode.endswith(".JK") else [kode]

        found_ticker = None
        for tc in ticker_candidates:
            cur2 = conn.execute(
                "SELECT ticker FROM instrument_master WHERE ticker = ?", (tc,)
            )
            result = cur2.fetchone()
            if result:
                found_ticker = result[0]
                break

        if not found_ticker:
            not_found += 1
            continue

        # Only update if ipo_date is not already set (don't overwrite existing data)
        cur3 = conn.execute(
            "SELECT ipo_date FROM instrument_master WHERE ticker = ?", (found_ticker,)
        )
        existing_ipo = cur3.fetchone()[0]

        if existing_ipo is not None:
            skipped += 1
            continue

        if not dry_run:
            conn.execute(
                """UPDATE instrument_master
                   SET ipo_date = ?, ipo_price = ?,
                       listing_date = COALESCE(listing_date, ?),
                       updated_at = datetime('now')
                   WHERE ticker = ?""",
                (ipo_date, ipo_price, ipo_date, found_ticker),
            )
        updated += 1

    # Also sync from mm_listing if it exists
    mm_updated = 0
    cur_mm = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='mm_listing'"
    )
    if cur_mm.fetchone() and not dry_run:
        mm_rows = conn.execute(
            """SELECT ml.ticker, ml.listing_date, ml.delisting_date
               FROM mm_listing ml
               WHERE ml.ticker IS NOT NULL"""
        ).fetchall()

        for ticker, listing_date, delisting_date in mm_rows:
            # Try with .JK suffix
            tc = ticker if ticker.endswith(".JK") else f"{ticker}.JK"
            cur4 = conn.execute(
                "SELECT ticker FROM instrument_master WHERE ticker = ?", (tc,)
            )
            if cur4.fetchone():
                conn.execute(
                    """UPDATE instrument_master
                       SET listing_date = COALESCE(listing_date, ?),
                           delisting_date = COALESCE(delisting_date, ?),
                           updated_at = datetime('now')
                       WHERE ticker = ?""",
                    (listing_date, delisting_date, tc),
                )
                mm_updated += 1

    if not dry_run:
        conn.commit()

    conn.close()

    result = {
        "updated": updated,
        "skipped": skipped,
        "not_found": not_found,
        "total_legacy": total_legacy,
        "mm_listing_updated": mm_updated,
    }

    print(f"\nSync results{' (DRY RUN)' if dry_run else ''}:")
    print(f"  Legacy stock_ipo records: {total_legacy}")
    print(f"  Updated instrument_master: {updated}")
    print(f"  Skipped (already had IPO data): {skipped}")
    print(f"  Not found in instrument_master: {not_found}")
    if mm_updated:
        print(f"  mm_listing → instrument_master: {mm_updated} listing/delisting dates synced")

    return result


def main():
    parser = argparse.ArgumentParser(description="Sync IPO data from stock_ipo → instrument_master")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--db-path", default=str(DB_PATH), help="Path to SQLite database")
    args = parser.parse_args()

    sync_ipo_data(Path(args.db_path), dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
