# Test Plan — Trading System (v0.1.10)

> **Total:** 600+ unit tests across 45 test files + E2E tests via Playwright.
> **Framework:** pytest + Hypothesis (property-based) + Playwright (E2E)
> **Coverage gate:** minimum 50% (`pyproject.toml`)

---

## Core Engine Tests

| Engine | Test File | Test Cases |
|--------|-----------|-----------|
| Technical Analysis | `test_technical.py` | RSI, MACD, MA, ADX, Bollinger Bands, volume profile, trend classification |
| Fundamental Analysis | `test_fundamental.py` | yfinance fetch, fallback to `saham_snapshot`/`idx_financial_statements`, scoring |
| Sentiment Engine | `test_sentiment.py` | Indonesian NLP lexicon, negation handling, multi-source weighting, IDX historical |
| Decision Engine | `test_decision.py` | Multi-factor weighted scoring, regime filter, BUY/HOLD/WATCHLIST/AVOID, conviction threshold |
| Risk Engine | `test_risk.py` | VaR, CVaR, position sizing, stop-loss, take-profit, risk flags |
| Cost Model | `test_costs.py` | Broker fees, levy, PPh, slippage estimation, feasibility check |
| Portfolio Engine | `test_portfolio.py` | Equity calculation, cash tracking, position management |
| Rebalancer | `test_rebalancer.py` | Target weights, drift detection, rebalance execution, toggle |
| Performance & Watchlist | `test_performance_watchlist.py` | Sharpe, drawdown, win rate, equity curve, watchlist CRUD |
| XAI Engine | `test_xai.py` | Narrative generation, top factors extraction |
| AI Learning | `test_ai_learning.py` | LR weight optimization, coefficient clipping, OOS validation, regime weights |
| Backtest Engine | `test_backtest.py` | BuyAndHold, MA Crossover, Conviction strategy, warmup, point-in-time safety |
| Corporate Actions | `test_corporate.py` | Splits, dividends, fetch & store |
| Monitoring | `test_monitoring.py` | Health check, source status |
| Paper Trading | `test_paper_trading.py` | State persistence, P&L tracking |

## Execution Tests

| Engine | Test File | Test Cases |
|--------|-----------|-----------|
| Execution Engine | `test_execution.py` | Fees, slippage, simulate_fill, check_feasibility |
| Execution Interface | `test_execution_interface.py` | TradingInterface, PaperExecutionEngine, RealExecutionEngine, factory `get_execution_engine()` |
| Automated Execution | `test_automated_execution.py` | Robot trader, process_signal, monitor_positions, stop-loss/take-profit/trailing, daily loss limit |
| Broker Adapter | `test_broker_adapter.py` | MockBrokerAdapter, authenticate, cash balance, positions, order execution, get_broker_adapter factory |

## Data Layer Tests

| Component | Test File | Test Cases |
|-----------|-----------|-----------|
| Data Storage | `test_storage.py` | OHLCV CRUD, scores, positions, orders, audit log, source health |
| Data Validation | `test_validation.py` | Completeness, plausibility, cross-source, reconciliation |
| Data Source Adapter | `test_data_source_adapter.py` | Yahoo Finance adapter, rate limiting, retry, error handling |
| Archive | `test_archive.py` | Parquet export, archive adapter, file management |
| Import Legacy | `test_import_legacy.py` | LegacyDataImporter, saham.db import, row count validation |

## API & CLI Tests

| Component | Test File | Test Cases |
|-----------|-----------|-----------|
| API Endpoints | `test_api.py` | All 78 endpoints, health, scores, recommendations, paper-trade, backtest, extended data, circuit breaker, CRUD |
| CRUD Operations | `test_crud_operations.py` | Delete OHLCV, scores, orders, positions, audit logs, AI weights, equity snapshots, risk metrics, archive, relationships, corporate actions, news |
| CLI | `test_cli.py` | All 15 subcommands: fetch, list, compute-scores, corporate-actions, update-adjusted-close, import-legacy, relationship, recommend, explain, monitor, paper-trade, backtest, execution, test-e2e, schedule |

## TIP Component Tests (Layer 1–6)

Tests untuk komponen yang diadopsi dari TIP/swing/ML/GitHub. Dikonsolidasi ke 6 file berdasarkan layer.

### Layer 1 — `test_layer1_tip.py`

| ID | Komponen | Class | Test Cases |
|----|----------|-------|------------|
| CC | Data Quality Engine | `TestDataQualityEngine` | empty df, duplicates, zero prices, negative prices, high<low, missing bars, stale data, abnormal returns, summary string |
| DD | Rate Limiter | `TestYFinanceRateLimiter` | min delay, jitter, window limit, circuit breaker open/half-open/closed, exponential backoff, per-symbol failure, from_env, reset |

### Layer 2 — `test_layer2_tip.py`

| ID | Komponen | Class | Test Cases |
|----|----------|-------|------------|
| K | Advanced Technical | `TestAdvancedTechnical` | Ichimoku, Williams %R, OBV, ADX, Stochastic RSI, multi-timeframe |
| F | Enhanced Regime | `TestEnhancedRegime` | z-score computation, stale data gate, coverage gate, risk_on/risk_off/neutral classification, config versioning |
| X | Factor Engine | `TestFactorEngine` | momentum 1M/3M/6M/12M, low_volatility, quality, beta, size, value proxy, percentile rank, composite, liquidity filter, min history |

### Layer 3 — `test_layer3_tip.py`

| ID | Komponen | Class | Test Cases |
|----|----------|-------|------------|
| Y | Alpha Composer | `TestAlphaComposer` | regime multiplier, sector multiplier, factor weights, min_composite_score gate, min_confidence gate, reason codes, version |
| Z | No-Trade Engine | `TestNoTradeEngine` | regime blocklist, low confidence, low alpha, low liquidity, insufficient history, stale data, event risk, model disagreement, data quality fail, batch evaluate |

### Layer 4 — `test_layer4_tip.py`

| ID | Komponen | Class | Test Cases |
|----|----------|-------|------------|
| FF | Enhanced Risk Engine | `TestEnhancedRiskEngine` | vol-targeted sizing, sector cap, cash allocation by regime, stop loss, trailing stop, portfolio vol, beta guard, drawdown guard, transaction cost |
| EE | Alpha Validation Lab | `TestAlphaValidationLab` | VALID/WATCH/REJECT decision, leakage test, survivorship test, OOS sharpe, robustness, cost-adjusted sharpe, thresholds override |

### Layer 5 — `test_layer5_tip.py`

| ID | Komponen | Class | Test Cases |
|----|----------|-------|------------|
| N | Alpha-Adjusted Labeling | `TestLabeling` | forward return labeling, alpha-adjusted labels, triple-barrier |
| S | Deep Learning Models | `TestDeepLearning` | LSTM shape, train/predict, scaling |
| T | Ensemble System | `TestEnsemble` | voting, stacking, weight optimization |
| L | Model Registry | `TestModelRegistry` | register, version, load, compare |

### Layer 6 — `test_layer6_tip.py`

| ID | Komponen | Class | Test Cases |
|----|----------|-------|------------|
| C | Purged Time Series Split | `TestPurgedKFold` | purging, embargo, fold overlap |
| D | Walk-Forward Validator | `TestWalkForward` | rolling window, expanding window, OOS metrics |
| V | Trading Expectancy | `TestTradingExpectancy` | win rate, R:R, expectancy, Kelly |
| H | Performance Attribution | `TestPerformanceAttribution` | factor attribution, sector attribution |
| I | Correlation Position Sizing | `TestCorrelationPositionSizing` | correlation matrix, diversification ratio |
| AA | Cross-Asset Engine | `TestCrossAsset` | equity-bond, FX, commodity correlation |
| BB | Lead-Lag Analyzer | `TestLeadLag` | cross-correlation, lag detection, significance |
| M | Manipulation Detector | `TestManipulation` | volume anomaly, marking close, pump-dump, wash trading |
| Q | Factor Screener | `TestFactorScreener` | screen, filter, rank |

### Standalone TIP Component Tests

| ID | Komponen | Test File | Test Cases |
|----|----------|-----------|------------|
| U | Order Book Analyzer | `test_order_book.py` | spread, depth, imbalance |
| P | Email Notification | `test_notifier.py` / `test_email_notification.py` | SMTP send, template, fallback |
| E | Stateful Paper Trading | `test_paper_trading.py` | state persistence, P&L tracking |
| W | World Monitor Patterns | `test_world_monitor.py` | 7-signal composite, CII |

## Phase 6 Tests

| Component | Test File | Test Cases |
|-----------|-----------|------------|
| Broker Adapter | `test_broker_adapter.py` | MockBrokerAdapter, authenticate, balance, positions, orders, factory |
| CRUD Operations | `test_crud_operations.py` | Delete endpoints for all resources (OHLCV, scores, orders, positions, audit, AI weights, snapshots, risk, archive, relationships, corporate actions, news) |

## P2 Fix Tests

| Fix | Test File | Test Cases |
|-----|-----------|------------|
| P2-1: Adjusted Close | `test_p2_1_adjusted_close.py` | Adjusted close calculation, update, backfill |
| P2-2: Data Source Adapter | `test_p2_2_data_source.py` | Yahoo Finance adapter, retry, error handling |
| P2-3: WAL + Alembic | `test_p2_3_wal_alembic.py` | WAL mode, Alembic migration, schema versioning |
| P2-5: WebSocket + Cache + Pagination | `test_p2_5_ws_cache_pagination.py` | WebSocket live updates, cache invalidation, pagination |

## Property-Based Tests

| Component | Test File | Framework | Invariants |
|-----------|-----------|-----------|------------|
| Backtest Engine | `test_property_based.py` | Hypothesis | Equity never negative, PnL consistent with trades, trade count >= 0, final equity = initial + sum(realized_pnl) - fees, win rate in [0,1] |

## Ported Modules Tests

| Component | Test File | Test Cases |
|-----------|-----------|------------|
| Ported Modules | `test_ported_modules.py` | Cross-module integration, import validation, basic functionality |

## E2E Tests (Playwright)

**Directory:** `tests/e2e/`

| File | Test Cases |
|------|------------|
| `test_dashboard.py` | Dashboard load, ticker switch, chart render, API integration |
| `comprehensive_test.py` | Full E2E: backtest, Monte Carlo, walk-forward, execution, risk simulation |
| `capture_console_errors.py` | Console error capture during page interaction |
| `record_demo.py` | Demo recording: dashboard, analyze, ticker switch |
| `run_all.py` | Simulation suite runner |

---

## Running Tests

```bash
# All unit tests
python -m pytest tests/unit/ -v

# With coverage
python -m pytest tests/unit/ --cov=trading_system --cov-report=term-missing

# Specific layer
python -m pytest tests/unit/test_layer1_tip.py -v

# Property-based
python -m pytest tests/unit/test_property_based.py -v

# E2E (requires backend + frontend running)
python -m pytest tests/e2e/test_dashboard.py -v

# Comprehensive E2E
python tests/e2e/comprehensive_test.py

# Simulation suite
python tests/e2e/run_all.py
```

## CI Pipeline

GitHub Actions (`.github/workflows/ci.yml`):
1. `ruff check` — lint + format
2. `mypy` — type checking
3. `pytest` — unit tests with coverage gate (50%)
4. Frontend lint + build
5. Docker build verification
