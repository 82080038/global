"""Render data: fetch dari internet untuk semua tabel kosong yang bisa diisi.

Menggunakan rate limiter untuk menghormati batas API:
- yfinance: 0.3s delay (calibrated via stress test, ~3.3 req/sec)
- IDX scraper: 0.2s delay (curl_cffi bypass + 3x retry for Cloudflare)
- RSS feeds: 1.0s delay (polite to third-party feed servers)

Tabel yang akan di-render:
1. corporate_actions + dividends  → yfinance (splits + dividends per ticker)
2. fundamental_data               → yfinance (info, financials, balance, cashflow)
3. technical_indicators           → compute dari OHLCV yang ada (no internet)
4. scores                         → AnalysisPipeline.compute() (per ticker)
5. relationship_matrix            → MarketRelationshipEngine.compute()
6. foreign_flow                   → IDX scraper (jika cloudscraper available)
7. news                           → RSS feeds (jika feedparser available)
8. source_health                  → auto-filled saat fetch
9. instrument_master              → dari watchlist + ticker list
10. market_calendar               → compute dari OHLCV dates

Usage:
    python scripts/render_data.py                    # render semua
    python scripts/render_data.py --tickers BBCA.JK  # render untuk ticker tertentu
    python scripts/render_data.py --only corporate   # hanya corporate actions
    python scripts/render_data.py --dry-run           # lihat apa yang akan dilakukan
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

# Force unbuffered stdout for real-time terminal output
sys.stdout.reconfigure(line_buffering=True)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from trading_system.config import (
    DEFAULT_BENCHMARK,
    DEFAULT_GLOBAL_TICKERS,
    DEFAULT_MACRO_TICKERS,
)
from trading_system.data.adaptive_rate_limiter import AdaptiveRateLimiter
from trading_system.data.storage import DataStorage

# Rate limiters (adaptive, auto-tuning)
_yf_limiter = AdaptiveRateLimiter.for_yfinance()
_idx_limiter = AdaptiveRateLimiter.for_idx_scraper()
_rss_limiter = AdaptiveRateLimiter.for_rss()

# Legacy delays kept for compatibility (now derived from limiters)
YFINANCE_DELAY = 0.0  # handled by _yf_limiter
IDX_DELAY = 0.0       # handled by _idx_limiter
RSS_DELAY = 0.0       # handled by _rss_limiter


def get_target_tickers(storage: DataStorage, limit: int | None = None) -> list[str]:
    """Get active IDX stock tickers + non-equity reference tickers.
    
    Excludes:
    - Delisted/suspended tickers (is_active=0)
    - Tickers not in instrument_master (orphaned OHLCV)
    
    Returns tickers with .JK suffix for IDX stocks (yfinance format).
    """
    # Active IDX stocks (equity, is_active=1) — add .JK suffix for yfinance
    idx_codes = storage.load_idx_stock_tickers(active_only=True)
    idx_stocks = [f"{c}.JK" if "." not in c else c for c in idx_codes]
    # Non-equity reference tickers (indices, commodities, forex, etf)
    non_equity = [t["ticker"] for t in storage.load_non_equity_tickers()]
    
    tickers = idx_stocks + non_equity
    if limit:
        tickers = tickers[:limit]
    return tickers


def render_ohlcv(storage: DataStorage, tickers: list[str], dry_run: bool = False):
    """Fetch OHLCV data for tickers (Parquet-first, fallback Yahoo Finance).
    
    Uses AnalysisPipeline.ensure_ohlcv() which:
    1. Check if SQLite already has today's data → skip
    2. Try Parquet archive for incremental data
    3. Fallback to Yahoo Finance for latest data
    4. Auto-saves to both SQLite and Parquet
    """
    from trading_system.analysis.pipeline import AnalysisPipeline

    pipeline = AnalysisPipeline(storage)
    total = 0
    skipped = 0
    errors = 0

    for i, ticker in enumerate(tickers):
        if dry_run:
            # Check staleness
            df = storage.load_ohlcv(ticker)
            if not df.empty:
                last_ts = str(df.index[-1])[:10]
                from datetime import datetime
                today = datetime.now().strftime("%Y-%m-%d")
                if last_ts >= today:
                    print(f"  [DRY-RUN] {ticker}: up to date ({last_ts})")
                    skipped += 1
                else:
                    print(f"  [DRY-RUN] {ticker}: stale (last={last_ts}), would fetch")
                    total += 1
            else:
                print(f"  [DRY-RUN] {ticker}: no data, would fetch")
                total += 1
            continue

        try:
            ok = pipeline.ensure_ohlcv(ticker, period="2y")
            if ok:
                df = storage.load_ohlcv(ticker)
                n = len(df)
                total += 1
                if (i + 1) % 100 == 0 or (i + 1) == len(tickers):
                    print(f"  [{i+1}/{len(tickers)}] {ticker}: {n:,} rows OK")
            else:
                errors += 1
                print(f"  [{i+1}/{len(tickers)}] {ticker}: FAILED to fetch OHLCV")
        except Exception as e:
            errors += 1
            if (i + 1) % 100 == 0 or (i + 1) == len(tickers):
                print(f"  [{i+1}/{len(tickers)}] {ticker}: ERROR - {e}")
        _yf_limiter._wait_delay()

    print(f"  Total OHLCV fetched: {total}, skipped (up to date): {skipped}, errors: {errors}")
    return total


def render_corporate_actions(storage: DataStorage, tickers: list[str], dry_run: bool = False):
    """Fetch corporate actions (splits + dividends) from yfinance."""
    from trading_system.corporate.actions import CorporateActionEngine

    engine = CorporateActionEngine(storage)
    total = 0
    dividends_total = 0
    for i, ticker in enumerate(tickers):
        if dry_run:
            print(f"  [DRY-RUN] {ticker}: would fetch corporate actions")
            continue
        try:
            result = engine.fetch(ticker)
            count = result.get("count", 0)
            total += count
            # Also save dividends to dividends table
            for action in result.get("actions", []):
                if action.get("action_type") == "dividend":
                    storage.save_dividend({
                        "ticker": ticker,
                        "ex_date": action.get("ex_date"),
                        "amount": action.get("value"),
                        "currency": "IDR" if ticker.endswith(".JK") else "USD",
                        "source": "yfinance",
                    })
                    dividends_total += 1
            print(f"  [{i+1}/{len(tickers)}] {ticker}: {count} actions ({dividends_total} dividends so far)")
        except Exception as e:
            print(f"  [{i+1}/{len(tickers)}] {ticker}: ERROR - {e}")
        _yf_limiter._wait_delay()
    print(f"  Total corporate actions: {total}, dividends: {dividends_total}")
    return total


def render_fundamental(storage: DataStorage, tickers: list[str], dry_run: bool = False):
    """Fetch fundamental data from yfinance and save to DB."""
    import yfinance as yf

    total = 0
    for i, ticker in enumerate(tickers):
        if dry_run:
            print(f"  [DRY-RUN] {ticker}: would fetch fundamental data")
            continue
        try:
            t = yf.Ticker(ticker)
            info = t.info or {}
            if not info:
                print(f"  [{i+1}/{len(tickers)}] {ticker}: no info")
                _yf_limiter._wait_delay()
                continue

            # Save to fundamental_data table
            record = {
                "ticker": ticker,
                "date": datetime.now(UTC).strftime("%Y-%m-%d"),
                "pe_ratio": info.get("trailingPE") or info.get("forwardPE"),
                "pb_ratio": info.get("priceToBook"),
                "roe": info.get("returnOnEquity"),
                "debt_to_equity": info.get("debtToEquity"),
                "dividend_yield": info.get("dividendYield"),
                "revenue": info.get("totalRevenue"),
                "net_profit": info.get("netIncomeToCommon"),
                "total_assets": info.get("totalAssets"),
                "total_liabilities": info.get("totalLiab"),
                "cash_flow": info.get("operatingCashflow"),
                "source": "yfinance",
            }
            storage.save_fundamental(record)
            total += 1
            pe = record.get("pe_ratio")
            roe = record.get("roe")
            print(f"  [{i+1}/{len(tickers)}] {ticker}: OK (PE={pe}, ROE={roe})")
        except Exception as e:
            print(f"  [{i+1}/{len(tickers)}] {ticker}: ERROR - {e}")
        _yf_limiter._wait_delay()
    print(f"  Total fundamental records: {total}")
    return total


def render_technical_indicators(storage: DataStorage, tickers: list[str], dry_run: bool = False):
    """Compute technical indicators from existing OHLCV data (no internet needed)."""
    from trading_system.analysis.technical import TechnicalAnalysisEngine

    engine = TechnicalAnalysisEngine()
    total = 0
    for i, ticker in enumerate(tickers):
        if dry_run:
            print(f"  [DRY-RUN] {ticker}: would compute technical indicators")
            continue
        try:
            df = storage.load_ohlcv(ticker)
            if df.empty or len(df) < 50:
                print(f"  [{i+1}/{len(tickers)}] {ticker}: insufficient data ({len(df)} rows)")
                continue
            engine.load_ohlcv(storage, ticker)
            indicators = engine.compute_indicators()
            # Save last row of indicators
            last = indicators.iloc[-1]
            ts = str(df.index[-1])[:10]  # strip time component
            record = {
                "ticker": ticker,
                "timestamp": ts,
                "ma_20": float(last.get("ma_20", 0)) if pd.notna(last.get("ma_20")) else None,
                "ma_50": float(last.get("ma_50", 0)) if pd.notna(last.get("ma_50")) else None,
                "rsi": float(last.get("rsi", 50)) if pd.notna(last.get("rsi")) else None,
                "macd": float(last.get("macd", 0)) if pd.notna(last.get("macd")) else None,
                "macd_signal": float(last.get("macd_signal", 0)) if pd.notna(last.get("macd_signal")) else None,
                "adx": float(last.get("adx", 0)) if pd.notna(last.get("adx")) else None,
                "atr_14": float(last.get("atr_14", 0)) if pd.notna(last.get("atr_14")) else None,
                "bb_upper": float(last.get("bb_upper", 0)) if pd.notna(last.get("bb_upper")) else None,
                "bb_lower": float(last.get("bb_lower", 0)) if pd.notna(last.get("bb_lower")) else None,
                "volume_sma_20": float(last.get("volume_sma_20", 0)) if pd.notna(last.get("volume_sma_20")) else None,
                "volume_ratio": float(last.get("volume_ratio", 1)) if pd.notna(last.get("volume_ratio")) else None,
                "volatility_20": float(last.get("volatility_20", 0)) if pd.notna(last.get("volatility_20")) else None,
            }
            storage.save_technical_indicator(record)
            total += 1
            print(f"  [{i+1}/{len(tickers)}] {ticker}: RSI={record['rsi']:.1f}, ADX={record['adx']:.1f}")
        except Exception as e:
            print(f"  [{i+1}/{len(tickers)}] {ticker}: ERROR - {e}")
    print(f"  Total technical indicators: {total}")
    return total


def render_scores(storage: DataStorage, tickers: list[str], dry_run: bool = False):
    """Run AnalysisPipeline.compute() for each ticker (includes fetch + all engines)."""
    from trading_system.analysis.pipeline import AnalysisPipeline

    pipeline = AnalysisPipeline(storage)
    total = 0
    for i, ticker in enumerate(tickers):
        if dry_run:
            print(f"  [DRY-RUN] {ticker}: would compute all scores")
            continue
        try:
            result = pipeline.compute(ticker, period="2y")
            if result["status"] == "ok":
                scores = result["scores"]
                score_str = ", ".join(f"{k}={v:.0f}" for k, v in scores.items() if v is not None)
                print(f"  [{i+1}/{len(tickers)}] {ticker}: {score_str}")
                total += 1
            else:
                print(f"  [{i+1}/{len(tickers)}] {ticker}: {result.get('message', 'failed')}")
        except Exception as e:
            print(f"  [{i+1}/{len(tickers)}] {ticker}: ERROR - {e}")
        _yf_limiter._wait_delay()
    print(f"  Total scored tickers: {total}")
    return total


def render_relationships(storage: DataStorage, tickers: list[str], dry_run: bool = False):
    """Compute relationship matrix (correlations with global/macro assets)."""
    from trading_system.analysis.relationship import MarketRelationshipEngine

    engine = MarketRelationshipEngine(storage)
    total = 0
    for i, ticker in enumerate(tickers):
        if dry_run:
            print(f"  [DRY-RUN] {ticker}: would compute relationships")
            continue
        try:
            result = engine.compute(ticker)
            if result["status"] == "ok":
                rels = result.get("relationships", [])
                print(f"  [{i+1}/{len(tickers)}] {ticker}: {len(rels)} relationships, score={result['score']:.1f}")
                total += 1
            else:
                print(f"  [{i+1}/{len(tickers)}] {ticker}: {result.get('message', 'failed')}")
        except Exception as e:
            print(f"  [{i+1}/{len(tickers)}] {ticker}: ERROR - {e}")
    print(f"  Total relationship records: {total}")
    return total


def render_foreign_flow(storage: DataStorage, tickers: list[str], dry_run: bool = False):
    """Scrape foreign flow from IDX.co.id (requires cloudscraper)."""
    try:
        from trading_system.data.idx_scraper import scrape_foreign_flow, DEFAULT_STOCKS
    except ImportError:
        print("  [SKIP] cloudscraper not installed")
        return 0

    # Extract bare tickers (without .JK)
    idx_stocks = [t.replace(".JK", "") for t in tickers if t.endswith(".JK")]
    # Use default stock list or our tickers
    stocks = idx_stocks[:50] if idx_stocks else DEFAULT_STOCKS  # limit for rate limiting

    if dry_run:
        print(f"  [DRY-RUN] Would scrape foreign flow for {len(stocks)} stocks")
        return 0

    try:
        df = scrape_foreign_flow(
            start_date="2025-01-02",
            stocks=stocks,
            delay=_idx_limiter.min_delay,
        )
        if df.empty:
            print("  No foreign flow data retrieved")
            return 0

        # Save to SQLite
        for _, row in df.iterrows():
            storage.save_foreign_flow(row.to_dict())
        print(f"  Foreign flow records: {len(df)}")
        return len(df)
    except Exception as e:
        print(f"  ERROR: {e}")
        return 0


def render_news(storage: DataStorage, tickers: list[str], dry_run: bool = False):
    """Fetch news from RSS feeds (requires feedparser)."""
    try:
        import feedparser
    except ImportError:
        print("  [SKIP] feedparser not installed")
        return 0

    from trading_system.sentiment.engine import RSS_FEEDS

    if dry_run:
        print(f"  [DRY-RUN] Would fetch news from {len(RSS_FEEDS)} RSS feeds")
        return 0

    total = 0
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            print(f"  Feed: {feed_url} ({len(feed.entries)} entries)")
            for entry in feed.entries[:20]:
                news_id = entry.get("id") or entry.get("link", "")
                if not news_id:
                    continue
                record = {
                    "news_id": str(news_id)[:200],
                    "headline": entry.get("title", ""),
                    "body": entry.get("summary", ""),
                    "published_at": entry.get("published", ""),
                    "source": feed_url,
                    "entities": "",
                    "topic": "",
                    "sentiment": None,
                    "impact": None,
                }
                storage.save_news(record)
                total += 1
        except Exception as e:
            print(f"  Feed error: {e}")
        _rss_limiter._wait_delay()

    print(f"  Total news articles: {total}")
    return total


def render_instrument_master(storage: DataStorage, tickers: list[str], dry_run: bool = False):
    """Populate instrument_master: add missing tickers and fill sector/industry for existing ones."""
    import yfinance as yf

    existing = set(storage.load_instrument_master_tickers())
    # Tickers not in IM at all
    missing = [t for t in tickers if t.replace(".JK", "") not in existing and t not in existing]
    # Tickers in IM but without sector info — need to enrich
    import sqlite3
    from trading_system.config import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    no_sector = set(r[0] for r in conn.execute(
        "SELECT ticker FROM instrument_master WHERE sector IS NULL OR sector = ''"
    ).fetchall())
    conn.close()
    # Map OHLCV tickers to IM tickers (strip .JK)
    enrich = [t for t in tickers if t.replace(".JK", "") in no_sector]

    if dry_run:
        print(f"  [DRY-RUN] Would add {len(missing)} new, enrich {len(enrich)} existing")
        return 0

    total = 0
    # Phase 1: Add missing tickers
    for i, ticker in enumerate(missing):
        try:
            t = yf.Ticker(ticker)
            info = t.info or {}
            bare = ticker.replace(".JK", "")
            record = {
                "ticker": bare,
                "name": info.get("longName") or info.get("shortName") or ticker,
                "sector": info.get("sector", ""),
                "subsector": info.get("industry", ""),
                "exchange": info.get("exchange", "IDX" if ticker.endswith(".JK") else "GLOBAL"),
                "market_cap": info.get("marketCap"),
            }
            storage.save_instrument_master(record)
            total += 1
            print(f"  [NEW {i+1}/{len(missing)}] {bare}: {record['name']}")
        except Exception as e:
            print(f"  [NEW {i+1}/{len(missing)}] {ticker}: ERROR - {e}")
        _yf_limiter._wait_delay()

    # Phase 2: Enrich existing tickers with sector/industry/market_cap
    for i, ticker in enumerate(enrich):
        bare = ticker.replace(".JK", "")
        try:
            t = yf.Ticker(ticker)
            info = t.info or {}
            if not info:
                continue
            record = {
                "ticker": bare,
                "name": info.get("longName") or info.get("shortName") or bare,
                "sector": info.get("sector", ""),
                "subsector": info.get("industry", ""),
                "exchange": info.get("exchange", "IDX"),
                "market_cap": info.get("marketCap"),
            }
            storage.save_instrument_master(record)
            total += 1
            if (i + 1) % 25 == 0:
                print(f"  [ENRICH {i+1}/{len(enrich)}] {bare}: sector={record['sector']}")
        except Exception as e:
            if (i + 1) % 25 == 0:
                print(f"  [ENRICH {i+1}/{len(enrich)}] {ticker}: ERROR - {e}")
        _yf_limiter._wait_delay()

    print(f"  Total instrument master records: {total}")
    return total


def render_broker_flow(storage: DataStorage, tickers: list[str], dry_run: bool = False):
    """Scrape broker flow from IDX.co.id (requires cloudscraper)."""
    try:
        from trading_system.data.idx_batch import IDXBatchEngine
    except ImportError:
        print("  [SKIP] idx_batch not available")
        return 0

    idx_stocks = [t.replace(".JK", "") for t in tickers if t.endswith(".JK")]
    if not idx_stocks:
        print("  [SKIP] No IDX stocks in target list")
        return 0

    if dry_run:
        print(f"  [DRY-RUN] Would scrape broker flow for {len(idx_stocks)} IDX stocks")
        return len(idx_stocks)

    engine = IDXBatchEngine(delay=_idx_limiter.min_delay)
    result = engine.scrape_broker_flow(
        start_date=datetime.now(UTC).strftime("%Y-%m-%d"),
        tickers=idx_stocks,
    )
    total = result.get("saved", 0)
    print(f"  Broker flow scraped: {total} records")
    return total


def render_pattern_analysis(storage: DataStorage, tickers: list[str], dry_run: bool = False):
    """Compute pattern analysis from OHLCV data (no internet needed)."""
    from trading_system.analysis.order_book import OrderBookAnalyzer

    analyzer = OrderBookAnalyzer()
    total = 0
    for i, ticker in enumerate(tickers):
        if dry_run:
            print(f"  [DRY-RUN] {ticker}: would compute pattern analysis")
            continue
        try:
            df = storage.load_ohlcv(ticker)
            if df.empty or len(df) < 30:
                continue
            patterns = analyzer.detect_pattern_blocks(df)
            for p in patterns[-5:]:  # save last 5 patterns
                record = {
                    "ticker": ticker,
                    "date": str(df.index[-1])[:10],
                    "pattern_type": p.get("type", "UNKNOWN"),
                    "confidence": p.get("pattern_strength", 0),
                    "direction": p.get("direction", "neutral"),
                    "details": str(p),
                    "source": "order_book_analyzer",
                }
                storage.save_pattern_analysis(record)
            total += len(patterns[-5:])
            if (i + 1) % 100 == 0:
                print(f"  [{i+1}/{len(tickers)}] {ticker}: {len(patterns)} patterns detected")
        except Exception as e:
            if (i + 1) % 100 == 0:
                print(f"  [{i+1}/{len(tickers)}] {ticker}: ERROR - {e}")
    print(f"  Total pattern analysis records: {total}")
    return total


def render_macro_data(storage: DataStorage, tickers: list[str], dry_run: bool = False):
    """Fetch macro economic data (Yahoo Finance proxy tickers + compute indicators)."""
    from trading_system.config import DEFAULT_MACRO_TICKERS

    total = 0
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    for label, ticker in DEFAULT_MACRO_TICKERS.items():
        if dry_run:
            print(f"  [DRY-RUN] {label} ({ticker}): would fetch macro data")
            total += 1
            continue
        try:
            df = storage.load_ohlcv(ticker)
            if not df.empty:
                last_val = float(df["close"].iloc[-1])
                record = {
                    "series_name": label,
                    "date": str(df.index[-1])[:10],
                    "value": last_val,
                    "unit": "index" if label not in ("USD_IDR",) else "IDR/USD",
                    "source": "yfinance",
                    "frequency": "daily",
                }
                storage.save_macro_data(record)
                total += 1
                print(f"  {label} ({ticker}): {last_val:.4f}")
            _yf_limiter._wait_delay()
        except Exception as e:
            print(f"  {label} ({ticker}): ERROR - {e}")

    print(f"  Total macro data records: {total}")
    return total


def render_fear_greed(storage: DataStorage, tickers: list[str], dry_run: bool = False):
    """Compute Fear & Greed index from market breadth indicators.
    
    Uses IHSG (^JKSE) data: momentum, volatility, volume, market breadth.
    """
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    if dry_run:
        print(f"  [DRY-RUN] Would compute Fear & Greed for {today}")
        return 1

    try:
        df = storage.load_ohlcv("^JKSE")
        if df.empty or len(df) < 20:
            print("  [SKIP] Insufficient IHSG data for Fear & Greed")
            return 0

        # Compute components
        returns = df["close"].pct_change().dropna()
        recent_returns = returns.tail(10)
        momentum = float(recent_returns.mean() * 100)
        volatility = float(recent_returns.std() * 100)
        rsi_like = float(100 - (100 / (1 + max(0, recent_returns.tail(5).mean() / max(0.001, recent_returns.tail(5).std())))))

        # Volume trend
        vol_recent = df["volume"].tail(10).mean()
        vol_hist = df["volume"].tail(60).mean()
        vol_ratio = float(vol_recent / max(1, vol_hist))

        # Composite: 0-100 (0=extreme fear, 100=extreme greed)
        fg_value = 50 + (momentum * 2) - (volatility * 0.5) + ((vol_ratio - 1) * 10)
        fg_value = max(0, min(100, fg_value))

        if fg_value < 25:
            classification = "Extreme Fear"
        elif fg_value < 45:
            classification = "Fear"
        elif fg_value < 55:
            classification = "Neutral"
        elif fg_value < 75:
            classification = "Greed"
        else:
            classification = "Extreme Greed"

        record = {
            "tanggal": today,
            "nilai": int(round(fg_value)),
            "label": classification,
        }
        storage.save_fear_greed(record)
        print(f"  Fear & Greed: {fg_value:.2f} ({classification})")
        return 1
    except Exception as e:
        print(f"  ERROR: {e}")
        return 0


def render_esg_scores(storage: DataStorage, tickers: list[str], dry_run: bool = False):
    """Fetch ESG scores from yfinance sustainability data."""
    import yfinance as yf

    total = 0
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    for i, ticker in enumerate(tickers):
        if dry_run:
            print(f"  [DRY-RUN] {ticker}: would fetch ESG scores")
            total += 1
            continue
        try:
            t = yf.Ticker(ticker)
            sust = t.sustainability
            if sust is not None and not sust.empty:
                e_score = s_score = g_score = esg_score = None
                try:
                    esg_score = float(sust.loc["esgScores"]["EsgScores"])
                except Exception:
                    pass
                try:
                    e_score = float(sust.loc["environmentScore"]["EnvironmentScore"])
                except Exception:
                    pass
                try:
                    s_score = float(sust.loc["socialScore"]["SocialScore"])
                except Exception:
                    pass
                try:
                    g_score = float(sust.loc["governanceScore"]["GovernanceScore"])
                except Exception:
                    pass

                if any(v is not None for v in [e_score, s_score, g_score, esg_score]):
                    record = {
                        "kode": ticker.replace(".JK", ""),
                        "year": int(datetime.now(UTC).year),
                        "rating_agency": "yfinance",
                        "rating": None,
                        "score": esg_score,
                    }
                    storage.save_esg_score(record)
                    total += 1
                    if (i + 1) % 50 == 0:
                        print(f"  [{i+1}/{len(tickers)}] {ticker}: ESG={esg_score}")
        except Exception:
            pass
        _yf_limiter._wait_delay()

    print(f"  Total ESG scores: {total}")
    return total


def render_corporate_governance(storage: DataStorage, tickers: list[str], dry_run: bool = False):
    """Fetch corporate governance info from yfinance."""
    import yfinance as yf

    total = 0
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    for i, ticker in enumerate(tickers):
        if dry_run:
            print(f"  [DRY-RUN] {ticker}: would fetch governance data")
            total += 1
            continue
        try:
            t = yf.Ticker(ticker)
            info = t.info or {}
            board_size = info.get("boardSize")
            if not board_size:
                # Try to infer from numberOfDirectors
                board_size = info.get("numberOfDirectors")

            # Compute ownership concentration from institutional ownership
            inst = t.institutional_holders
            ownership_concentration = None
            if inst is not None and not inst.empty:
                try:
                    top_pct = float(inst["Value Pct"].head(5).sum()) if "Value Pct" in inst.columns else None
                    ownership_concentration = top_pct
                except Exception:
                    pass

            if board_size or ownership_concentration:
                record = {
                    "kode": ticker.replace(".JK", ""),
                    "year": int(datetime.now(UTC).year),
                    "board_commissioners": board_size,
                    "independent_commissioners": info.get("independentDirectors"),
                    "board_directors": board_size,
                    "gcg_score": "standard",
                    "has_whistleblowing": 0,
                    "has_risk_committee": 0,
                }
                storage.save_corporate_governance(record)
                total += 1
                if (i + 1) % 50 == 0:
                    print(f"  [{i+1}/{len(tickers)}] {ticker}: board={board_size}")
        except Exception:
            pass
        _yf_limiter._wait_delay()

    print(f"  Total governance records: {total}")
    return total


def render_external_events(storage: DataStorage, tickers: list[str], dry_run: bool = False):
    """Fetch external events from RSS feeds (global market events)."""
    try:
        import feedparser
    except ImportError:
        print("  [SKIP] feedparser not installed")
        return 0

    FEEDS = [
        ("https://feeds.reuters.com/reuters/businessNews", "reuters_business", "global"),
        ("https://feeds.reuters.com/reuters/companyNews", "reuters_company", "global"),
        ("https://www.cnbc.com/id/10001147/device/rss/rss.html", "cnbc_markets", "global"),
    ]

    if dry_run:
        print(f"  [DRY-RUN] Would fetch from {len(FEEDS)} RSS feeds")
        return len(FEEDS)

    total = 0
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    for url, source, region in FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:20]:
                event_id = entry.get("id", entry.get("link", ""))[:200]
                record = {
                    "tanggal": entry.get("published", today)[:10] if entry.get("published") else today,
                    "kategori": "market_news",
                    "judul": entry.get("title", ""),
                    "lokasi": region,
                    "dampak_market": "medium",
                    "sektor": "",
                    "deskripsi": entry.get("summary", "")[:500],
                }
                storage.save_external_event(record)
                total += 1
            _rss_limiter._wait_delay()
        except Exception as e:
            print(f"  {source}: ERROR - {e}")

    print(f"  Total external events: {total}")
    return total


def render_policy_events(storage: DataStorage, tickers: list[str], dry_run: bool = False):
    """Fetch policy events from RSS feeds (BI/OJK/Indonesian government)."""
    try:
        import feedparser
    except ImportError:
        print("  [SKIP] feedparser not installed")
        return 0

    FEEDS = [
        ("https://www.bi.go.id/en/rss/berita", "bi_news", "BI"),
        ("https://www.ojk.go.id/en/berita-dan-kegiatan/siaran-pers/Pages/RSS.aspx", "ojk_press", "OJK"),
    ]

    if dry_run:
        print(f"  [DRY-RUN] Would fetch from {len(FEEDS)} policy RSS feeds")
        return len(FEEDS)

    total = 0
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    for url, source, instansi in FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:20]:
                record = {
                    "date": entry.get("published", today)[:10] if entry.get("published") else today,
                    "event_type": "policy",
                    "description": entry.get("title", ""),
                    "instansi": instansi,
                    "dampak": "medium",
                    "sektor": "",
                    "deskripsi": entry.get("summary", "")[:500],
                    "source": source,
                }
                storage.save_external_event({
                    "tanggal": record["date"],
                    "kategori": "policy",
                    "judul": record["description"],
                    "lokasi": "ID",
                    "dampak_market": record["dampak"],
                    "sektor": "",
                    "deskripsi": record.get("deskripsi", ""),
                })
                total += 1
            _rss_limiter._wait_delay()
        except Exception as e:
            print(f"  {source}: ERROR - {e}")

    print(f"  Total policy events: {total}")
    return total


def render_stock_personality(storage: DataStorage, tickers: list[str], dry_run: bool = False):
    """Compute stock personality from OHLCV data (volatility, beta, liquidity)."""
    import numpy as np

    total = 0
    for i, ticker in enumerate(tickers):
        if dry_run:
            print(f"  [DRY-RUN] {ticker}: would compute personality")
            total += 1
            continue
        try:
            df = storage.load_ohlcv(ticker)
            if df.empty or len(df) < 60:
                continue

            returns = df["close"].pct_change().dropna()
            avg_vol = float(returns.tail(60).std() * np.sqrt(252))  # annualized vol
            avg_volume = float(df["volume"].tail(60).mean())

            # Beta vs IHSG
            ihsg = storage.load_ohlcv("^JKSE")
            beta = correlation = None
            if not ihsg.empty and len(ihsg) >= 60:
                ihsg_ret = ihsg["close"].pct_change().dropna()
                # Align dates
                common = returns.index.intersection(ihsg_ret.index)
                if len(common) >= 30:
                    r_aligned = returns.loc[common]
                    i_aligned = ihsg_ret.loc[common]
                    cov = float(np.cov(r_aligned, i_aligned)[0, 1])
                    var_i = float(i_aligned.var())
                    beta = cov / max(0.0001, var_i) if var_i > 0 else None
                    correlation = float(r_aligned.corr(i_aligned))

            # Classify
            if avg_vol > 0.5:
                vol_profile = "high_volatility"
            elif avg_vol > 0.25:
                vol_profile = "moderate_volatility"
            else:
                vol_profile = "low_volatility"

            if avg_volume > 1e9:
                liq_profile = "high_liquidity"
            elif avg_volume > 1e8:
                liq_profile = "moderate_liquidity"
            else:
                liq_profile = "low_liquidity"

            if beta and beta > 1.2:
                ptype = "aggressive"
            elif beta and beta < 0.8:
                ptype = "defensive"
            else:
                ptype = "balanced"

            record = {
                "kode": ticker.replace(".JK", ""),
                "profile_date": datetime.now(UTC).strftime("%Y-%m-%d"),
                "avg_daily_volatility": round(avg_vol, 4),
                "volatility_regime": vol_profile,
                "trend_bias": ptype,
                "trend_strength": abs(beta) if beta else None,
                "beta_vs_ihsg": round(beta, 3) if beta else None,
                "correlation_ihsg": round(correlation, 3) if correlation else None,
                "avg_volume": round(avg_volume, 0),
                "liquidity_score": liq_profile,
                "personality_label": ptype,
            }
            storage.save_stock_personality(record)
            total += 1
            if (i + 1) % 100 == 0:
                print(f"  [{i+1}/{len(tickers)}] {ticker}: {ptype} (beta={beta:.2f})" if beta else f"  [{i+1}/{len(tickers)}] {ticker}: {ptype}")
        except Exception as e:
            if (i + 1) % 100 == 0:
                print(f"  [{i+1}/{len(tickers)}] {ticker}: ERROR - {e}")

    print(f"  Total stock personalities: {total}")
    return total


def render_sector_master(storage: DataStorage, tickers: list[str], dry_run: bool = False):
    """Populate sector_master with IDX sector classifications (static data)."""
    IDX_SECTORS = [
        ("AGRI", "Agriculture", "", "Plantation, livestock, fisheries"),
        ("MINING", "Mining", "", "Coal, metals, oil & gas mining"),
        ("BASIC", "Basic Industry", "", "Chemicals, cement, metals, pulp"),
        ("CYCLICAL", "Cyclical Consumer Goods", "", "Automotive, apparel, home goods"),
        ("NONCYCLICAL", "Non-Cyclical Consumer Goods", "", "Food, beverage, tobacco, retail"),
        ("FINANCE", "Financials", "", "Banks, insurance, securities"),
        ("PROPERTY", "Property & Real Estate", "", "Property developers, construction"),
        ("INFRA", "Infrastructure", "", "Telecom, transport, utilities"),
        ("TECH", "Technology", "", "IT services, software, electronics"),
        ("HEALTH", "Healthcare", "", "Pharma, hospitals, medical devices"),
        ("MISC", "Miscellaneous", "", "Conglomerates, other sectors"),
    ]

    if dry_run:
        print(f"  [DRY-RUN] Would insert {len(IDX_SECTORS)} IDX sectors")
        return len(IDX_SECTORS)

    total = 0
    for code, name, parent, desc in IDX_SECTORS:
        record = {
            "kode": code,
            "nama": name,
            "deskripsi": desc,
        }
        storage.save_sector(record)
        total += 1

    print(f"  Total sector_master records: {total}")
    return total


def render_market_calendar(storage: DataStorage, tickers: list[str], dry_run: bool = False):
    """Generate IDX market calendar (trading days + holidays) for current year."""
    from datetime import datetime, timedelta
    import pandas as pd

    # IDX holidays 2026 (static — update annually)
    IDX_HOLIDAYS_2026 = {
        "2026-01-01": "Tahun Baru",
        "2026-02-08": "Tahun Baru Imlek",
        "2026-02-17": "Isra Mikraj",
        "2026-03-03": "Hari Suci Nyepi",
        "2026-03-20": "Wafat Isa Almasih",
        "2026-03-21": "Jumat Agung",
        "2026-04-10": "Hari Raya Idul Fitri",
        "2026-04-13": "Cuti Idul Fitri",
        "2026-04-14": "Cuti Idul Fitri",
        "2026-04-15": "Cuti Idul Fitri",
        "2026-05-01": "Hari Buruh",
        "2026-05-20": "Kenaikan Isa Almasih",
        "2026-05-27": "Hari Raya Waisak",
        "2026-06-01": "Hari Lahir Pancasila",
        "2026-06-17": "Hari Raya Idul Adha",
        "2026-07-07": "Tahun Baru Hijriyah",
        "2026-08-17": "Hari Kemerdekaan RI",
        "2026-09-27": "Maulid Nabi Muhammad",
        "2026-12-25": "Hari Raya Natal",
    }

    year = datetime.now().year
    if dry_run:
        print(f"  [DRY-RUN] Would generate calendar for {year} ({len(IDX_HOLIDAYS_2026)} holidays)")
        return 365

    total = 0
    start = datetime(year, 1, 1)
    end = datetime(year, 12, 31)
    current = start
    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        weekday = current.weekday()
        is_trading = weekday < 5 and date_str not in IDX_HOLIDAYS_2026  # Mon-Fri, not holiday
        holiday_name = IDX_HOLIDAYS_2026.get(date_str, None)

        record = {
            "date": date_str,
            "exchange": "IDX",
            "is_trading_day": 1 if is_trading else 0,
            "holiday_name": holiday_name,
            "half_day": 0,
        }
        storage.save_market_calendar(record)
        total += 1
        current += timedelta(days=1)

    print(f"  Total market_calendar records: {total} ({year})")
    return total


def main():
    parser = argparse.ArgumentParser(description="Render data from internet to database")
    parser.add_argument("--tickers", nargs="*", help="Specific tickers (default: all in DB)")
    parser.add_argument("--limit", type=int, help="Limit number of tickers")
    parser.add_argument("--only", choices=["ohlcv", "corporate", "fundamental", "technical",
                                            "scores", "relationships", "foreign_flow",
                                            "news", "instrument_master",
                                            "broker_flow", "pattern_analysis", "macro_data",
                                            "fear_greed", "esg_scores", "corporate_governance",
                                            "external_events", "policy_events",
                                            "stock_personality", "sector_master",
                                            "market_calendar"],
                        help="Only render specific data type")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--bootstrap", action="store_true",
                        help="Load OHLCV from Parquet archive first (for new machine setup)")
    parser.add_argument("--force", action="store_true",
                        help="Force render all tickers, ignoring staleness check")
    parser.add_argument("--max-age", type=float, default=24,
                        help="Max age in hours before data is considered stale (default: 24)")
    args = parser.parse_args()

    storage = DataStorage()

    # Bootstrap: load OHLCV from Parquet if requested
    if args.bootstrap:
        from trading_system.data.archive import ArchiveAdapter
        from trading_system.data.validation import DataQualityValidator
        from trading_system.data.acquisition import normalize_ohlcv
        from trading_system.config import DATA_ARCHIVE_DIR

        print("=" * 70)
        print(f"BOOTSTRAP: Loading OHLCV from Parquet archive")
        print(f"Archive: {DATA_ARCHIVE_DIR}")
        print("=" * 70)

        archive = ArchiveAdapter()
        validator = DataQualityValidator()
        arch_tickers = archive.list_archived_tickers()
        print(f"Found {len(arch_tickers)} tickers in archive")

        loaded = 0
        for i, t in enumerate(arch_tickers):
            try:
                df = archive.load_ohlcv(t)
                if df.empty:
                    continue
                df = df.reset_index()
                if "ticker" not in df.columns:
                    df["ticker"] = t
                if "asset_class" not in df.columns:
                    df["asset_class"] = "equity"
                if "exchange" not in df.columns:
                    df["exchange"] = "INDO" if t.endswith(".JK") else "GLOBAL"
                if "timeframe" not in df.columns:
                    df["timeframe"] = "1d"
                if "source" not in df.columns:
                    df["source"] = "archive"
                if "ingested_at" not in df.columns:
                    df["ingested_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")
                if "data_quality_score" not in df.columns:
                    df["data_quality_score"] = None
                raw = normalize_ohlcv(df)
                clean, report = validator.validate(raw)
                if report.action != "pause":
                    storage.save_ohlcv(clean)
                    loaded += 1
                if (i + 1) % 100 == 0:
                    print(f"  [{i+1}/{len(arch_tickers)}] loaded {loaded} tickers")
            except Exception as e:
                pass
        print(f"Bootstrap: {loaded}/{len(arch_tickers)} tickers loaded from Parquet")

    # Determine target tickers
    if args.tickers:
        tickers = args.tickers
    else:
        tickers = get_target_tickers(storage, limit=args.limit)

    print("=" * 70)
    print(f"RENDER DATA {'[DRY-RUN]' if args.dry_run else ''}")
    print(f"Target tickers: {len(tickers)}")
    print(f"Rate limits: yfinance={_yf_limiter.min_delay}s, IDX={_idx_limiter.min_delay}s, RSS={_rss_limiter.min_delay}s")
    print("=" * 70)

    tasks = {
        "ohlcv": ("OHLCV Data (Parquet-first, fallback yfinance)", render_ohlcv),
        "corporate": ("Corporate Actions + Dividends", render_corporate_actions),
        "fundamental": ("Fundamental Data", render_fundamental),
        "technical": ("Technical Indicators", render_technical_indicators),
        "scores": ("Analysis Scores (all engines)", render_scores),
        "relationships": ("Relationship Matrix", render_relationships),
        "foreign_flow": ("Foreign Flow (IDX scraper)", render_foreign_flow),
        "news": ("News (RSS feeds)", render_news),
        "instrument_master": ("Instrument Master", render_instrument_master),
        "broker_flow": ("Broker Flow (IDX scraper)", render_broker_flow),
        "pattern_analysis": ("Pattern Analysis (computed from OHLCV)", render_pattern_analysis),
        "macro_data": ("Macro Economic Data", render_macro_data),
        "fear_greed": ("Fear & Greed Index (computed)", render_fear_greed),
        "esg_scores": ("ESG Scores (yfinance)", render_esg_scores),
        "corporate_governance": ("Corporate Governance (yfinance)", render_corporate_governance),
        "external_events": ("External Events (RSS feeds)", render_external_events),
        "policy_events": ("Policy Events (BI/OJK RSS)", render_policy_events),
        "stock_personality": ("Stock Personality (computed)", render_stock_personality),
        "sector_master": ("Sector Master (IDX sectors)", render_sector_master),
        "market_calendar": ("Market Calendar (IDX)", render_market_calendar),
    }

    if args.only:
        tasks = {args.only: tasks[args.only]}

    # Map task keys to render_log table names
    task_table_map = {
        "ohlcv": "ohlcv",
        "corporate": "corporate_actions",
        "fundamental": "fundamental_data",
        "technical": "technical_indicators",
        "scores": "scores",
        "relationships": "relationship_matrix",
        "foreign_flow": "foreign_flow",
        "news": "news",
        "instrument_master": "instrument_master",
        "broker_flow": "broker_flow",
        "pattern_analysis": "pattern_analysis",
        "macro_data": "macro_data",
        "fear_greed": "fear_greed",
        "esg_scores": "esg_scores",
        "corporate_governance": "corporate_governance",
        "external_events": "external_events",
        "policy_events": "policy_events",
        "stock_personality": "stock_personality",
        "sector_master": "sector_master",
        "market_calendar": "market_calendar",
    }

    # Tasks that are not per-ticker (global/market-wide)
    non_ticker_tasks = {"fear_greed", "sector_master", "market_calendar",
                        "external_events", "policy_events", "macro_data"}

    results = {}
    for key, (label, func) in tasks.items():
        print(f"\n{'-' * 70}")
        print(f"[{label}]")
        print(f"{'-' * 70}")

        if key in non_ticker_tasks:
            # Non-ticker tasks: check staleness via a single '__global__' entry
            if args.force or args.dry_run:
                should_run = True
            else:
                table_name = task_table_map.get(key, key)
                last = storage.get_last_rendered("__global__", table_name)
                if last:
                    from datetime import datetime as _dt, timedelta as _td
                    age = _dt.now(UTC) - _dt.fromisoformat(last)
                    should_run = age > _td(hours=args.max_age)
                else:
                    should_run = True
                if not should_run:
                    print(f"  Fresh (last rendered < {args.max_age}h ago) — skipping")

            if not should_run:
                results[key] = 0
                continue

            try:
                results[key] = func(storage, tickers, dry_run=args.dry_run)
                if not args.dry_run:
                    storage.log_render("__global__", task_table_map.get(key, key), status="ok")
            except Exception as e:
                print(f"  FATAL: {e}")
                results[key] = 0
            continue

        # Per-ticker tasks: filter to stale tickers only (unless --force)
        if args.force or args.dry_run:
            task_tickers = tickers
            stale_count = len(tickers)
        else:
            table_name = task_table_map.get(key, key)
            task_tickers = storage.get_stale_tickers(table_name, tickers, max_age_hours=args.max_age)
            stale_count = len(task_tickers)
            fresh_count = len(tickers) - stale_count
            print(f"  Stale: {stale_count} tickers  |  Fresh (skipped): {fresh_count}  |  Max age: {args.max_age}h")

        if not task_tickers:
            print(f"  All tickers are fresh — nothing to render")
            results[key] = 0
            continue

        try:
            results[key] = func(storage, task_tickers, dry_run=args.dry_run)
            # Log render for each ticker if not dry-run
            if not args.dry_run:
                table_name = task_table_map.get(key, key)
                for t in task_tickers:
                    storage.log_render(t, table_name, status="ok")
        except Exception as e:
            print(f"  FATAL: {e}")
            results[key] = 0

    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    for key, count in results.items():
        label = tasks[key][0]
        print(f"  {label:40s} {count:>10,}")
    print(f"\nDone at {datetime.now(UTC).isoformat()}")


if __name__ == "__main__":
    main()
