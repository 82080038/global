"""Add D1-D31 tables for legacy data import (§13.4 #3).

Creates tables needed for importing data from Parquet archive
(data_pasar_modal, TIP, swing, ML repos).

Revision ID: 0002_d1_d31
Revises: 0001_initial
Create Date: 2026-08-01

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_d1_d31"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create tables for D1-D31 legacy data import."""

    # D1: Instrument Master
    op.execute("""
        CREATE TABLE IF NOT EXISTS instrument_master (
            ticker TEXT PRIMARY KEY,
            name TEXT,
            sector TEXT,
            subsector TEXT,
            exchange TEXT,
            listing_date TEXT,
            delisting_date TEXT,
            is_active INTEGER DEFAULT 1,
            board TEXT,
            market_cap REAL,
            free_float REAL,
            updated_at TEXT
        )
    """)

    # D2: Fundamental Data
    op.execute("""
        CREATE TABLE IF NOT EXISTS fundamental_data (
            ticker TEXT,
            date TEXT,
            pe_ratio REAL,
            pb_ratio REAL,
            roe REAL,
            debt_to_equity REAL,
            dividend_yield REAL,
            earnings_per_share REAL,
            book_value_per_share REAL,
            net_profit REAL,
            revenue REAL,
            total_assets REAL,
            total_liabilities REAL,
            cash_flow REAL,
            fiscal_year INTEGER,
            quarter INTEGER,
            source TEXT,
            PRIMARY KEY (ticker, date, source)
        )
    """)

    # D3: Macro Data
    op.execute("""
        CREATE TABLE IF NOT EXISTS macro_data (
            series_name TEXT,
            date TEXT,
            value REAL,
            unit TEXT,
            source TEXT,
            frequency TEXT,
            PRIMARY KEY (series_name, date, source)
        )
    """)

    # D4: Foreign Flow
    op.execute("""
        CREATE TABLE IF NOT EXISTS foreign_flow (
            ticker TEXT,
            date TEXT,
            foreign_buy REAL,
            foreign_sell REAL,
            foreign_net REAL,
            domestic_buy REAL,
            domestic_sell REAL,
            domestic_net REAL,
            source TEXT,
            PRIMARY KEY (ticker, date, source)
        )
    """)

    # D5: Broker Flow
    op.execute("""
        CREATE TABLE IF NOT EXISTS broker_flow (
            ticker TEXT,
            date TEXT,
            broker TEXT,
            buy_volume REAL,
            buy_value REAL,
            sell_volume REAL,
            sell_value REAL,
            net_volume REAL,
            net_value REAL,
            source TEXT,
            PRIMARY KEY (ticker, date, broker, source)
        )
    """)

    # D6: Policy/Regulatory Events
    op.execute("""
        CREATE TABLE IF NOT EXISTS policy_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            event_type TEXT,
            description TEXT,
            impact TEXT,
            source TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # D7: Dividends
    op.execute("""
        CREATE TABLE IF NOT EXISTS dividends (
            ticker TEXT,
            ex_date TEXT,
            record_date TEXT,
            payment_date TEXT,
            amount REAL,
            currency TEXT,
            frequency TEXT,
            source TEXT,
            PRIMARY KEY (ticker, ex_date, source)
        )
    """)

    # D8: Sector Master
    op.execute("""
        CREATE TABLE IF NOT EXISTS sector_master (
            sector_code TEXT PRIMARY KEY,
            sector_name TEXT,
            parent_sector TEXT,
            description TEXT,
            updated_at TEXT
        )
    """)

    # D9: Market Calendar
    op.execute("""
        CREATE TABLE IF NOT EXISTS market_calendar (
            date TEXT PRIMARY KEY,
            exchange TEXT,
            is_trading_day INTEGER DEFAULT 1,
            holiday_name TEXT,
            half_day INTEGER DEFAULT 0,
            updated_at TEXT
        )
    """)

    # D10: Fear & Greed Index
    op.execute("""
        CREATE TABLE IF NOT EXISTS fear_greed (
            date TEXT PRIMARY KEY,
            value REAL,
            classification TEXT,
            source TEXT,
            updated_at TEXT
        )
    """)

    # D11: External Events
    op.execute("""
        CREATE TABLE IF NOT EXISTS external_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            event_type TEXT,
            description TEXT,
            region TEXT,
            impact_level TEXT,
            source TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # D12: ESG Scores
    op.execute("""
        CREATE TABLE IF NOT EXISTS esg_scores (
            ticker TEXT,
            date TEXT,
            e_score REAL,
            s_score REAL,
            g_score REAL,
            esg_score REAL,
            source TEXT,
            PRIMARY KEY (ticker, date, source)
        )
    """)

    # D13: Corporate Governance
    op.execute("""
        CREATE TABLE IF NOT EXISTS corporate_governance (
            ticker TEXT,
            date TEXT,
            board_size INTEGER,
            independent_directors INTEGER,
            audit_committee_quality TEXT,
            ownership_concentration REAL,
            source TEXT,
            PRIMARY KEY (ticker, date, source)
        )
    """)

    # D14: Stock Personality
    op.execute("""
        CREATE TABLE IF NOT EXISTS stock_personality (
            ticker TEXT PRIMARY KEY,
            personality_type TEXT,
            volatility_profile TEXT,
            liquidity_profile TEXT,
            beta REAL,
            correlation_to_ihsg REAL,
            updated_at TEXT
        )
    """)

    # D15: Trade Journal
    op.execute("""
        CREATE TABLE IF NOT EXISTS trade_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            entry_date TEXT,
            exit_date TEXT,
            entry_price REAL,
            exit_price REAL,
            quantity REAL,
            side TEXT,
            pnl REAL,
            return_pct REAL,
            strategy TEXT,
            notes TEXT,
            tags TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # D16: Pattern Analysis
    op.execute("""
        CREATE TABLE IF NOT EXISTS pattern_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            date TEXT,
            pattern_type TEXT,
            confidence REAL,
            direction TEXT,
            details TEXT,
            source TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # D17: Valuation Cache
    op.execute("""
        CREATE TABLE IF NOT EXISTS valuation_cache (
            ticker TEXT,
            date TEXT,
            method TEXT,
            intrinsic_value REAL,
            market_price REAL,
            upside_pct REAL,
            assumptions TEXT,
            source TEXT,
            PRIMARY KEY (ticker, date, method, source)
        )
    """)

    # D18: Technical Indicators (pre-computed)
    op.execute("""
        CREATE TABLE IF NOT EXISTS technical_indicators (
            ticker TEXT,
            date TEXT,
            indicator TEXT,
            value REAL,
            timeframe TEXT,
            source TEXT,
            PRIMARY KEY (ticker, date, indicator, timeframe, source)
        )
    """)

    # Create indexes for performance
    op.execute("CREATE INDEX IF NOT EXISTS idx_fundamental_ticker ON fundamental_data(ticker)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_fundamental_date ON fundamental_data(date)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_macro_series ON macro_data(series_name)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_macro_date ON macro_data(date)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_foreign_flow_ticker ON foreign_flow(ticker)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_foreign_flow_date ON foreign_flow(date)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_broker_flow_ticker ON broker_flow(ticker)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_broker_flow_date ON broker_flow(date)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_dividends_ticker ON dividends(ticker)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_trade_journal_ticker ON trade_journal(ticker)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_technical_indicators_ticker ON technical_indicators(ticker)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_technical_indicators_date ON technical_indicators(date)")

    # D19: Corporate Actions Legacy (from data_pasar_modal Parquet archive)
    op.execute("""
        CREATE TABLE IF NOT EXISTS corporate_actions_legacy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tanggal TEXT,
            kode TEXT,
            jenis TEXT,
            deskripsi TEXT,
            status TEXT,
            created_at TEXT
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_ca_legacy_kode ON corporate_actions_legacy(kode)")

    # D20: AI Scores Historical
    op.execute("""
        CREATE TABLE IF NOT EXISTS ai_scores_historical (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tanggal TEXT,
            kode TEXT,
            skor INTEGER,
            sinyal TEXT,
            alasan TEXT,
            faktor_makro REAL,
            faktor_fundamental REAL,
            faktor_teknikal REAL,
            faktor_sentimen REAL,
            faktor_global REAL,
            created_at TEXT
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_scores_hist_kode ON ai_scores_historical(kode)")

    # D21: Alerts Historical
    op.execute("""
        CREATE TABLE IF NOT EXISTS alerts_historical (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tanggal TEXT,
            tipe TEXT,
            kode TEXT,
            sektor TEXT,
            pesan TEXT,
            level TEXT,
            read_status INTEGER
        )
    """)

    # D22: Backtest Results Historical
    op.execute("""
        CREATE TABLE IF NOT EXISTS backtest_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT,
            strategy TEXT,
            total_return REAL,
            benchmark_return REAL,
            alpha REAL,
            sharpe_ratio REAL,
            max_drawdown REAL,
            win_rate REAL,
            total_trades INTEGER,
            details TEXT,
            created_at TEXT
        )
    """)


def downgrade() -> None:
    """Drop all D1-D31 tables."""
    tables = [
        "backtest_results",
        "alerts_historical",
        "ai_scores_historical",
        "corporate_actions_legacy",
        "technical_indicators",
        "valuation_cache",
        "pattern_analysis",
        "trade_journal",
        "stock_personality",
        "corporate_governance",
        "esg_scores",
        "external_events",
        "fear_greed",
        "market_calendar",
        "sector_master",
        "dividends",
        "policy_events",
        "broker_flow",
        "foreign_flow",
        "macro_data",
        "fundamental_data",
        "instrument_master",
    ]
    for table in tables:
        op.execute(f"DROP TABLE IF EXISTS {table}")
