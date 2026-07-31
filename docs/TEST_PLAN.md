# Test Plan per Komponen A–FF (§13.4 #5)

> Rencana test untuk setiap komponen yang diadopsi dari TIP/swing/ML/GitHub.

---

## Layer 1

| ID | Komponen | Test File | Test Cases |
|---|---|---|---|
| CC | Data Quality Engine | `test_quality_engine.py` | empty df, duplicates, zero prices, negative prices, high<low, missing bars, stale data, abnormal returns, summary string |
| DD | Rate Limiter | `test_rate_limiter.py` | min delay, jitter, window limit, circuit breaker open/half-open/closed, exponential backoff, per-symbol failure, from_env, reset |

## Layer 2

| ID | Komponen | Test File | Test Cases |
|---|---|---|---|
| K | Advanced Technical | `test_advanced_technical.py` | Ichimoku, Williams %R, OBV, ADX, Stochastic RSI, multi-timeframe |
| F | Enhanced Regime | `test_enhanced_regime.py` | z-score computation, stale data gate, coverage gate, risk_on/risk_off/neutral classification, config versioning |
| X | Factor Engine | `test_factor_engine.py` | momentum 1M/3M/6M/12M, low_volatility, quality, beta, size, value proxy, percentile rank, composite, liquidity filter, min history |

## Layer 3

| ID | Komponen | Test File | Test Cases |
|---|---|---|---|
| Y | Alpha Composer | `test_alpha_composer.py` | regime multiplier, sector multiplier, factor weights, min_composite_score gate, min_confidence gate, reason codes, version |
| Z | No-Trade Engine | `test_no_trade.py` | regime blocklist, low confidence, low alpha, low liquidity, insufficient history, stale data, event risk, model disagreement, data quality fail, batch evaluate |

## Layer 4

| ID | Komponen | Test File | Test Cases |
|---|---|---|---|
| FF | Enhanced Risk Engine | `test_enhanced_risk.py` | vol-targeted sizing, sector cap, cash allocation by regime, stop loss, trailing stop, portfolio vol, beta guard, drawdown guard, transaction cost |
| EE | Alpha Validation Lab | `test_alpha_validation.py` | VALID/WATCH/REJECT decision, leakage test, survivorship test, OOS sharpe, robustness, cost-adjusted sharpe, thresholds override |

## Layer 5

| ID | Komponen | Test File | Test Cases |
|---|---|---|---|
| N | Alpha-Adjusted Labeling | `test_alpha_labeling.py` | forward return labeling, alpha-adjusted labels, triple-barrier |
| C | Purged Time Series Split | `test_purged_tss.py` | purging, embargo, fold overlap |
| D | Walk-Forward Validator | `test_walk_forward.py` | rolling window, expanding window, OOS metrics |
| S | Deep Learning Models | `test_deep_learning.py` | LSTM shape, train/predict, scaling |
| T | Ensemble System | `test_ensemble.py` | voting, stacking, weight optimization |
| L | Model Registry | `test_model_registry.py` | register, version, load, compare |

## Layer 6

| ID | Komponen | Test File | Test Cases |
|---|---|---|---|
| U | Order Book Analyzer | `test_order_book.py` | spread, depth, imbalance |
| V | Trading Expectancy | `test_expectancy.py` | win rate, R:R, expectancy, Kelly |
| P | Email Notification | `test_notifier.py` | SMTP send, template, fallback |
| Q | Screener Templates | `test_screener.py` | breakout, oversold, volume spike |
| E | Stateful Paper Trading | `test_paper_trading.py` | state persistence, P&L tracking |
| H | Performance Attribution | `test_attribution.py` | factor attribution, sector attribution |
| I | Correlation Position Sizing | `test_corr_sizing.py` | correlation matrix, diversification ratio |
| AA | Cross-Asset Engine | `test_cross_asset.py` | equity-bond, FX, commodity correlation |
| BB | Lead-Lag Analyzer | `test_lead_lag.py` | cross-correlation, lag detection, significance |
| M | Manipulation Detector | `test_manipulation.py` | volume anomaly, marking close, pump-dump |
| W | World Monitor Patterns | `test_world_monitor.py` | 7-signal composite, CII |
