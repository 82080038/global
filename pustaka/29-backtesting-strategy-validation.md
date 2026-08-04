# Backtesting & Strategy Validation

> **Tujuan:** Dokumen ini adalah referensi definitif untuk backtesting dan validasi strategi trading — dari jenis backtest, common pitfalls (survivorship bias, look-ahead bias, overfitting), Monte Carlo simulation, walk-forward analysis, transaction cost modeling, hingga statistical significance testing — dengan implementasi kode untuk sistem trading Indonesia.

---

## Daftar Isi

1. [Konsep Backtesting](#1-konsep-backtesting)
2. [Jenis Backtest](#2-jenis-backtest)
3. [Common Pitfalls & Bias](#3-common-pitfalls--bias)
4. [Transaction Cost Modeling](#4-transaction-cost-modeling)
5. [Walk-Forward Analysis](#5-walk-forward-analysis)
6. [Monte Carlo Simulation](#6-monte-carlo-simulation)
7. [Statistical Significance](#7-statistical-significance)
8. [Performance Metrics](#8-performance-metrics)
9. [Regime-Aware Backtesting](#9-regime-aware-backtesting)
10. [Backtesting Framework](#10-backtesting-framework)
11. [Implementasi untuk IDX](#11-implementasi-untuk-idx)
12. [Checklist Implementasi](#12-checklist-implementasi)

---

## 1. Konsep Backtesting

### 1.1 Definisi

Backtesting adalah proses menguji strategi trading pada data historis untuk mengevaluasi performansi sebelum menerapkannya secara live.

```
Strategi + Data Historis → Simulasi → Hasil (Return, Risk, Drawdown)
                                        ↓
                                  Analisis & Validasi
                                        ↓
                                  Keputusan: Live / Reject / Improve
```

### 1.2 Prinsip Utama

| Prinsip | Deskripsi | Dampak jika Dilanggar |
|---------|-----------|----------------------|
| **No look-ahead** | Hanya gunakan info yang available saat keputusan | Backtest menipu, live gagal |
| **Realistic costs** | Include broker fee, spread, slippage, tax | Overstated return |
| **Survivorship inclusion** | Include delisted/suspended stocks | Survivorship bias |
| **Out-of-sample test** | Test pada data yang belum dilihat | Overfitting |
| **Multiple regimes** | Test across bull/bear/sideways | Regime-specific only |
| **Statistical rigor** | Assess significance, not just return | Lucky streak |

### 1.3 Backtesting vs Forward Testing

| Aspek | Backtesting | Forward Testing (Paper) |
|-------|-------------|-------------------------|
| **Data** | Historical | Real-time (simulated) |
| **Speed** | Seconds-minutes | Real-time (days/weeks) |
| **Cost** | None | Opportunity cost |
| **Bias** | Look-ahead, overfitting | Emotional, execution |
| **Purpose** | Strategy validation | System validation |
| **Best for** | Parameter tuning | End-to-end verification |

---

## 2. Jenis Backtest

### 2.1 Vectorized vs Event-Driven

| Aspek | Vectorized | Event-Driven |
|-------|-----------|-------------|
| **Speed** | Sangat cepat | Lambat |
| **Complexity** | Rendah | Tinggi |
| **Accuracy** | Moderate | Tinggi |
| **Order execution** | Simplified | Realistic (partial fills, latency) |
| **Best for** | Signal research, parameter scan | Production simulation, execution testing |

### 2.2 Vectorized Backtest

```python
def vectorized_backtest(
    df: pd.DataFrame,
    signals: pd.Series,
    initial_capital: float = 100_000_000,
    position_size: float = 0.10,  # 10% per trade
    fee_rate: float = 0.0025,
    slippage_rate: float = 0.001,
):
    """Fast vectorized backtest for signal research."""
    df = df.copy()
    df["signal"] = signals
    df["position"] = df["signal"].shift(1).fillna(0)  # enter next day
    
    # Returns
    df["asset_return"] = df["close"].pct_change()
    df["strategy_return"] = df["position"] * df["asset_return"]
    
    # Costs (only when position changes)
    df["trade"] = df["position"].diff().abs()
    df["cost"] = df["trade"] * (fee_rate + slippage_rate)
    df["strategy_return"] -= df["cost"]
    
    # Equity curve
    df["equity"] = initial_capital * (1 + df["strategy_return"]).cumprod()
    
    # Metrics
    total_return = (df["equity"].iloc[-1] / initial_capital - 1) * 100
    n_trades = int(df["trade"].sum() / 2)  # round trip = 2 trades
    
    return {
        "equity_curve": df["equity"],
        "total_return_pct": total_return,
        "n_trades": n_trades,
        "df": df,
    }
```

### 2.3 Event-Driven Backtest

```python
class EventDrivenBacktester:
    """Event-driven backtest with realistic execution."""
    
    def __init__(self, initial_capital: float, cost_model):
        self.capital = initial_capital
        self.cash = initial_capital
        self.positions = {}  # {ticker: {qty, entry_price}}
        self.trades = []
        self.equity_curve = []
        self.cost_model = cost_model
    
    def on_bar(self, date, ticker, bar_data):
        """Process a single bar."""
        # 1. Check open positions for SL/TP
        if ticker in self.positions:
            self._check_stops(ticker, bar_data, date)
        
        # 2. Process signal
        signal = self._get_signal(ticker, bar_data)
        if signal == "BUY" and ticker not in self.positions:
            self._execute_buy(ticker, bar_data, date)
        elif signal == "SELL" and ticker in self.positions:
            self._execute_sell(ticker, bar_data, date)
        
        # 3. Record equity
        self._record_equity(date)
    
    def _execute_buy(self, ticker, bar, date):
        price = bar["close"] * (1 + self.cost_model.slippage)
        qty = self._compute_position_size(price)
        
        if qty < 100:  # minimum lot
            return
        
        value = qty * price
        fee = value * self.cost_model.buy_fee
        total_cost = value + fee
        
        if total_cost > self.cash:
            return  # insufficient cash
        
        self.cash -= total_cost
        self.positions[ticker] = {"qty": qty, "entry_price": price}
        self.trades.append({
            "date": date, "ticker": ticker, "side": "BUY",
            "qty": qty, "price": price, "fee": fee,
        })
    
    def _execute_sell(self, ticker, bar, date):
        pos = self.positions[ticker]
        price = bar["close"] * (1 - self.cost_model.slippage)
        
        value = pos["qty"] * price
        fee = value * self.cost_model.sell_fee
        pph = value * 0.001  # PPh final 0.1%
        net = value - fee - pph
        
        self.cash += net
        realized_pnl = (price - pos["entry_price"]) * pos["qty"] - fee - pph
        
        self.trades.append({
            "date": date, "ticker": ticker, "side": "SELL",
            "qty": pos["qty"], "price": price, "fee": fee + pph,
            "realized_pnl": realized_pnl,
        })
        del self.positions[ticker]
    
    def _record_equity(self, date):
        market_value = sum(
            pos["qty"] * self._get_current_price(ticker)
            for ticker, pos in self.positions.items()
        )
        equity = self.cash + market_value
        self.equity_curve.append({"date": date, "equity": equity})
```

---

## 3. Common Pitfalls & Bias

### 3.1 Look-Ahead Bias

**Penyebab:** Menggunakan informasi yang belum available saat keputusan trading dibuat.

| Sumber | Contoh | Solusi |
|--------|--------|--------|
| **Future data** | Menggunakan close price hari ini untuk sinyal hari ini | Gunakan `shift(1)` |
| **Indicator lookahead** | SMA yang include hari ini untuk sinyal hari ini | Sinyal pada bar N, eksekusi pada bar N+1 |
| **Fundamental data** | Menggunakan earnings yang diumumkan 2 bulan setelah period | Gunakan announcement date, bukan period end |
| **Survivorship** | Hanya saham yang masih listed | Include delisted stocks |
| **Calendar lookahead** | Menggunakan holiday yang belum diumumkan | Gunakan historical calendar |

```python
# WRONG: look-ahead bias
df["signal"] = np.where(df["close"] > df["close"].rolling(20).mean(), 1, 0)
df["return"] = df["signal"] * df["close"].pct_change()  # same day return!

# CORRECT: signal today, execute tomorrow
df["signal"] = np.where(df["close"] > df["close"].rolling(20).mean(), 1, 0)
df["position"] = df["signal"].shift(1)  # enter next day
df["return"] = df["position"] * df["close"].pct_change()
```

### 3.2 Survivorship Bias

**Penyebab:** Backtest hanya pada saham yang masih listed saat backtest dijalankan. Saham yang delisted (bangkrut, suspend permanen) tidak included.

```python
# WRONG: only currently active tickers
tickers = storage.get_active_tickers()  # only is_active=1

# CORRECT: include all tickers that were active during backtest period
tickers = storage.get_tickers_active_between(start_date, end_date)
# This includes stocks that were listed but later delisted
```

### 3.3 Overfitting

**Penyebab:** Terlalu banyak parameter di-tune pada data yang sama.

| Symptom | Indikasi |
|---------|----------|
| Backtest return >> live return | Overfit |
| Sensitif terhadap parameter kecil | Overfit |
| Different period → very different result | Overfit |
| Too many rules/exceptions | Overfit |

```python
# Overfitting detection: parameter sensitivity
def parameter_sensitivity(df, param_name, param_range):
    """Test strategy across parameter range."""
    results = []
    for val in param_range:
        result = run_backtest(df, **{param_name: val})
        results.append({"param_value": val, "return": result["total_return"]})
    
    returns = [r["return"] for r in results]
    sensitivity = np.std(returns) / np.mean(returns) if np.mean(returns) != 0 else float('inf')
    
    return {
        "results": results,
        "sensitivity_ratio": sensitivity,
        "is_overfit": sensitivity > 0.5,  # high variation = overfit
    }
```

### 3.4 Data Snooping

**Penyebab:** Mencoba banyak strategi/variasi pada data yang sama, lalu memilih yang terbaik.

```python
# Multiple testing correction (Bonferroni)
def bonferroni_correction(p_values, alpha=0.05):
    """Correct for multiple hypothesis testing."""
    n_tests = len(p_values)
    corrected_alpha = alpha / n_tests
    significant = [p < corrected_alpha for p in p_values]
    return significant, corrected_alpha

# White's Reality Check or Hansen's SPA for strategy selection
# (advanced: bootstrap-based multiple testing correction)
```

---

## 4. Transaction Cost Modeling

### 4.1 Komponen Biaya

| Komponen | Rate IDX | Kapan | Model |
|----------|---------|-------|-------|
| **Broker fee (buy)** | 0.15-0.25% | Setiap beli | `% × value` |
| **Broker fee (sell)** | 0.15-0.25% | Setiap jual | `% × value` |
| **BEI levy** | 0.004% | Beli & jual | `% × value` |
| **PPh final** | 0.1% | Jual saja | `% × sell value` |
| **Slippage** | 0.05-0.5% | Market order | `f(size, liquidity)` |
| **Spread cost** | 0.05-0.5% | Market order | `half spread` |
| **Opportunity cost** | N/A | Limit unfill | `missed return` |

### 4.2 Cost Model Implementation

```python
@dataclass
class TransactionCostModel:
    """IDX transaction cost model."""
    buy_fee: float = 0.0015       # 0.15%
    sell_fee: float = 0.0025      # 0.25%
    levy: float = 0.00004         # 0.004%
    pph: float = 0.001            # 0.1% (sell only)
    slippage_bps: float = 5       # 0.05% base slippage
    
    def buy_cost(self, value: float) -> float:
        return value * (self.buy_fee + self.levy)
    
    def sell_cost(self, value: float) -> float:
        return value * (self.sell_fee + self.levy + self.pph)
    
    def slippage_cost(self, value: float, order_size: int, adv: int) -> float:
        """Square-root slippage model."""
        participation = order_size / adv if adv > 0 else 0
        slippage_pct = (self.slippage_bps / 10000) * np.sqrt(participation * 100)
        return value * slippage_pct
    
    def round_trip_cost_pct(self, value: float, order_size: int = 0, adv: int = 0) -> float:
        """Total round-trip cost as percentage."""
        buy = self.buy_cost(value) + self.slippage_cost(value, order_size, adv)
        sell = self.sell_cost(value) + self.slippage_cost(value, order_size, adv)
        return (buy + sell) / value * 100
```

### 4.3 Impact of Costs on Strategy

```python
def cost_impact_analysis(returns: pd.Series, cost_per_trade: float, trades_per_year: int):
    """Analyze how transaction costs erode returns."""
    gross_return = returns.sum() * 252  # annualized
    total_cost = cost_per_trade * trades_per_year
    net_return = gross_return - total_cost
    cost_drag = total_cost / gross_return * 100 if gross_return > 0 else 0
    
    return {
        "gross_return_pct": gross_return * 100,
        "total_cost_pct": total_cost * 100,
        "net_return_pct": net_return * 100,
        "cost_drag_pct": cost_drag,
        "trades_per_year": trades_per_year,
    }
```

> **Aturan praktis:** Jika biaya round-trip > 0.5% di IDX, strategi perlu return bruto > 2% per trade untuk profitable.

---

## 5. Walk-Forward Analysis

### 5.1 Konsep

Walk-forward analysis (WFA) mensimulasikan penggunaan strategi secara realistis:
1. Optimasi parameter pada window [t-k, t]
2. Test out-of-sample pada [t, t+h]
3. Slide window, re-optimasi, re-test
4. Aggregate semua out-of-sample results

```
Time →
Optimize: [========]          [========]          [========]
Test:              [====]              [====]              [====]
                   ↑                   ↑                   ↑
                   OOS 1               OOS 2               OOS 3
```

### 5.2 Implementasi

```python
def walk_forward_analysis(
    df: pd.DataFrame,
    strategy_fn,
    param_grid: dict,
    train_window: int = 252,   # 1 year
    test_window: int = 63,     # 3 months
    purge_gap: int = 5,        # 1 week purge
):
    """Walk-forward analysis with parameter optimization."""
    results = []
    n = len(df)
    
    for start in range(train_window + purge_gap, n, test_window):
        test_end = min(start + test_window, n)
        
        # Training window (with purge)
        train_start = start - train_window - purge_gap
        train_end = start - purge_gap
        train_data = df.iloc[train_start:train_end]
        test_data = df.iloc[start:test_end]
        
        # Optimize on training
        best_params = optimize_parameters(train_data, strategy_fn, param_grid)
        
        # Test out-of-sample
        test_result = strategy_fn(test_data, **best_params)
        
        results.append({
            "train_start": df.index[train_start],
            "train_end": df.index[train_end - 1],
            "test_start": df.index[start],
            "test_end": df.index[test_end - 1],
            "best_params": best_params,
            "test_return": test_result["total_return"],
            "test_sharpe": test_result["sharpe"],
            "test_max_dd": test_result["max_drawdown"],
        })
    
    # Aggregate
    oos_returns = [r["test_return"] for r in results]
    
    return {
        "windows": results,
        "n_windows": len(results),
        "oos_mean_return": np.mean(oos_returns),
        "oos_std_return": np.std(oos_returns),
        "oos_min_return": np.min(oos_returns),
        "oos_max_return": np.max(oos_returns),
        "oos_positive_rate": np.mean([r > 0 for r in oos_returns]),
        "is_robust": np.mean(oos_returns) > 0 and min(oos_returns) > -0.05,
    }
```

### 5.3 Walk-Forward Efficiency

```python
def walk_forward_efficiency(wfa_results: dict) -> float:
    """Walk-Forward Efficiency (WFE) = OOS return / IS return.
    
    WFE > 50% → strategy is robust
    WFE < 20% → likely overfit
    """
    is_returns = [r["train_return"] for r in wfa_results["windows"]]
    oos_returns = [r["test_return"] for r in wfa_results["windows"]]
    
    if np.mean(is_returns) == 0:
        return 0
    
    wfe = np.mean(oos_returns) / np.mean(is_returns) * 100
    return wfe
```

---

## 6. Monte Carlo Simulation

### 6.1 Tujuan

Monte Carlo simulation untuk backtesting:
- **Return resampling:** Acak urutan return untuk test distribusi hasil
- **Trade resampling:** Acak urutan trade untuk test drawdown distribution
- **Bootstrap:** Sample dengan replacement untuk confidence interval

### 6.2 Return Resampling

```python
def monte_carlo_returns(
    returns: pd.Series,
    n_simulations: int = 1000,
    initial_capital: float = 100_000_000,
):
    """Resample returns to generate distribution of outcomes."""
    final_values = []
    max_drawdowns = []
    
    for _ in range(n_simulations):
        # Shuffle returns
        shuffled = returns.sample(len(returns), replace=True).values
        
        # Build equity curve
        equity = initial_capital * np.cumprod(1 + shuffled)
        final_values.append(equity[-1])
        
        # Max drawdown
        peak = np.maximum.accumulate(equity)
        dd = (equity - peak) / peak
        max_drawdowns.append(dd.min())
    
    return {
        "final_values": final_values,
        "max_drawdowns": max_drawdowns,
        "median_final_value": np.median(final_values),
        "5th_percentile": np.percentile(final_values, 5),
        "95th_percentile": np.percentile(final_values, 95),
        "median_max_drawdown": np.median(max_drawdowns),
        "worst_max_drawdown": np.min(max_drawdowns),
        "prob_profit": np.mean([v > initial_capital for v in final_values]),
    }
```

### 6.3 Trade Resampling

```python
def monte_carlo_trades(trades: list, n_simulations: int = 1000):
    """Resample trade sequence to test drawdown robustness."""
    pnls = [t["realized_pnl"] for t in trades]
    
    max_drawdowns = []
    final_pnls = []
    
    for _ in range(n_simulations):
        shuffled = np.random.permutation(pnls)
        cumulative = np.cumsum(shuffled)
        
        peak = np.maximum.accumulate(cumulative)
        dd = cumulative - peak
        max_drawdowns.append(dd.min())
        final_pnls.append(cumulative[-1])
    
    return {
        "median_max_drawdown": np.median(max_drawdowns),
        "worst_5pct_drawdown": np.percentile(max_drawdowns, 5),
        "worst_drawdown": np.min(max_drawdowns),
        "median_final_pnl": np.median(final_pnls),
        "prob_profit": np.mean([p > 0 for p in final_pnls]),
    }
```

### 6.4 Position-Level Bootstrap

```python
def bootstrap_performance(
    returns: pd.Series,
    n_bootstrap: int = 1000,
    block_size: int = 5,  # block bootstrap for autocorrelation
):
    """Block bootstrap for Sharpe ratio confidence interval."""
    sharpe_ratios = []
    
    n = len(returns)
    for _ in range(n_bootstrap):
        # Block bootstrap
        blocks = []
        while sum(len(b) for b in blocks) < n:
            start = np.random.randint(0, n - block_size)
            blocks.append(returns.iloc[start:start + block_size].values)
        
        sample = np.concatenate(blocks)[:n]
        
        # Compute Sharpe
        mean_ret = np.mean(sample)
        std_ret = np.std(sample)
        sharpe = mean_ret / std_ret * np.sqrt(252) if std_ret > 0 else 0
        sharpe_ratios.append(sharpe)
    
    return {
        "sharpe_median": np.median(sharpe_ratios),
        "sharpe_5pct": np.percentile(sharpe_ratios, 5),
        "sharpe_95pct": np.percentile(sharpe_ratios, 95),
        "sharpe_std": np.std(sharpe_ratios),
    }
```

---

## 7. Statistical Significance

### 7.1 T-Test untuk Strategy Return

```python
from scipy import stats

def strategy_t_test(returns: pd.Series, benchmark: pd.Series, alpha=0.05):
    """Test if strategy outperforms benchmark significantly."""
    excess = returns - benchmark
    
    t_stat, p_value = stats.ttest_1samp(excess.dropna(), 0)
    
    return {
        "mean_excess_return": excess.mean(),
        "t_statistic": t_stat,
        "p_value": p_value,
        "is_significant": p_value < alpha,
        "alpha": alpha,
    }
```

### 7.2 Sharpe Ratio Significance

```python
def sharpe_ratio_significance(returns: pd.Series, rf: float = 0.06, alpha=0.05):
    """Test if Sharpe ratio is significantly different from zero."""
    excess = returns - rf / 252
    n = len(excess)
    
    sharpe = excess.mean() / excess.std() * np.sqrt(252) if excess.std() > 0 else 0
    
    # Jobson-Korkie test with Lipka correction
    # Simplified: t-stat = sharpe * sqrt(n) / sqrt(1 + 0.5 * sharpe^2)
    t_stat = sharpe * np.sqrt(n / 252) / np.sqrt(1 + 0.5 * sharpe**2 / 252)
    p_value = 2 * (1 - stats.norm.cdf(abs(t_stat)))
    
    return {
        "sharpe": sharpe,
        "t_statistic": t_stat,
        "p_value": p_value,
        "is_significant": p_value < alpha,
    }
```

### 7.3 Deflated Sharpe Ratio (López de Prado)

```python
def deflated_sharpe_ratio(
    sharpe: float,
    n: int,
    n_trials: int,  # number of strategies tested
    skewness: float = 0,
    kurtosis: float = 3,
):
    """Deflated Sharpe Ratio — adjusts for multiple testing.
    
    DSR = probability that observed Sharpe is above expected maximum
    of n_trials random strategies.
    """
    # Expected max Sharpe under null (Bailey & López de Prado)
    euler_gamma = 0.5772
    expected_max = np.sqrt(2 * np.log(n_trials)) - \
        (euler_gamma - np.log(2 * np.log(n_trials))) / \
        (2 * np.sqrt(2 * np.log(n_trials)))
    
    # Variance of Sharpe estimate
    var_sharpe = (1 - skewness * sharpe + (kurtosis - 1) / 4 * sharpe**2) / (n - 1)
    
    # Deflated Sharpe
    dsr = stats.norm.cdf((sharpe - expected_max) / np.sqrt(var_sharpe))
    
    return {
        "observed_sharpe": sharpe,
        "expected_max_sharpe": expected_max,
        "deflated_sharpe_ratio": dsr,
        "is_significant": dsr > 0.95,
        "n_trials": n_trials,
    }
```

---

## 8. Performance Metrics

### 8.1 Comprehensive Metrics

```python
def compute_all_metrics(
    returns: pd.Series,
    benchmark: pd.Series = None,
    rf: float = 0.06,  # risk-free rate (SBN 10Y)
    periods_per_year: int = 252,
):
    """Compute comprehensive performance metrics."""
    n = len(returns)
    total_return = (1 + returns).prod() - 1
    annual_return = (1 + total_return) ** (periods_per_year / n) - 1
    annual_vol = returns.std() * np.sqrt(periods_per_year)
    
    # Risk-adjusted
    excess = returns - rf / periods_per_year
    sharpe = excess.mean() / returns.std() * np.sqrt(periods_per_year) if returns.std() > 0 else 0
    
    # Sortino (downside deviation only)
    downside = returns[returns < 0]
    sortino = excess.mean() / downside.std() * np.sqrt(periods_per_year) if len(downside) > 0 and downside.std() > 0 else 0
    
    # Calmar (return / max drawdown)
    equity = (1 + returns).cumprod()
    peak = equity.cummax()
    drawdown = (equity - peak) / peak
    max_dd = drawdown.min()
    calmar = annual_return / abs(max_dd) if max_dd < 0 else 0
    
    # Win rate
    win_rate = (returns > 0).sum() / n * 100
    
    # Profit factor
    gains = returns[returns > 0].sum()
    losses = abs(returns[returns < 0].sum())
    profit_factor = gains / losses if losses > 0 else float('inf')
    
    metrics = {
        "total_return_pct": total_return * 100,
        "annual_return_pct": annual_return * 100,
        "annual_volatility_pct": annual_vol * 100,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "calmar_ratio": calmar,
        "max_drawdown_pct": max_dd * 100,
        "win_rate_pct": win_rate,
        "profit_factor": profit_factor,
        "n_periods": n,
    }
    
    # Benchmark comparison
    if benchmark is not None:
        alpha, beta = compute_alpha_beta(returns, benchmark, rf, periods_per_year)
        metrics.update({
            "alpha": alpha,
            "beta": beta,
            "excess_return_pct": (annual_return - (benchmark.mean() * periods_per_year)) * 100,
            "information_ratio": compute_information_ratio(returns, benchmark),
        })
    
    return metrics

def compute_alpha_beta(returns, benchmark, rf, periods):
    """Compute alpha and beta via regression."""
    excess_ret = returns - rf / periods
    excess_bench = benchmark - rf / periods
    
    beta = np.cov(excess_ret, excess_bench)[0, 1] / np.var(excess_bench)
    alpha = np.mean(excess_ret) - beta * np.mean(excess_bench)
    alpha_annual = alpha * periods
    
    return alpha_annual, beta

def compute_information_ratio(returns, benchmark):
    """Information ratio = excess return / tracking error."""
    excess = returns - benchmark
    tracking_error = excess.std()
    return excess.mean() / tracking_error * np.sqrt(252) if tracking_error > 0 else 0
```

### 8.2 Drawdown Analysis

```python
def drawdown_analysis(returns: pd.Series):
    """Detailed drawdown analysis."""
    equity = (1 + returns).cumprod()
    peak = equity.cummax()
    drawdown = (equity - peak) / peak
    
    # Find drawdown periods
    in_dd = drawdown < 0
    dd_periods = []
    start = None
    
    for i in range(len(drawdown)):
        if in_dd.iloc[i] and start is None:
            start = i
        elif not in_dd.iloc[i] and start is not None:
            dd_periods.append({
                "start": drawdown.index[start],
                "end": drawdown.index[i - 1],
                "duration_days": i - start,
                "max_drawdown": drawdown.iloc[start:i].min() * 100,
            })
            start = None
    
    return {
        "max_drawdown_pct": drawdown.min() * 100,
        "max_dd_duration_days": max(p["duration_days"] for p in dd_periods) if dd_periods else 0,
        "n_drawdown_periods": len(dd_periods),
        "avg_drawdown_pct": np.mean([p["max_drawdown"] for p in dd_periods]) if dd_periods else 0,
        "current_drawdown_pct": drawdown.iloc[-1] * 100,
        "recovery_factor": (equity.iloc[-1] / equity.max() - 1) * 100,
    }
```

---

## 9. Regime-Aware Backtesting

### 9.1 Mengapa Perlu Regime-Aware

Strategi yang profitable di bull market bisa hancur di bear market. Backtest harus test across regimes.

```python
def regime_aware_backtest(
    returns: pd.Series,
    regimes: pd.Series,
    strategy_returns: pd.Series,
):
    """Analyze strategy performance across different market regimes."""
    results = {}
    
    for regime in regimes.unique():
        mask = regimes == regime
        regime_returns = strategy_returns[mask]
        
        results[f"regime_{regime}"] = {
            "n_days": mask.sum(),
            "total_return_pct": (1 + regime_returns).prod() - 1,
            "annual_return_pct": regime_returns.mean() * 252 * 100,
            "volatility_pct": regime_returns.std() * np.sqrt(252) * 100,
            "sharpe": regime_returns.mean() / regime_returns.std() * np.sqrt(252) 
                if regime_returns.std() > 0 else 0,
            "max_drawdown_pct": ((1 + regime_returns).cumprod() / 
                (1 + regime_returns).cumprod().cummax() - 1).min() * 100,
            "win_rate_pct": (regime_returns > 0).sum() / len(regime_returns) * 100,
        }
    
    return results
```

### 9.2 Regime Labels

```python
REGIME_LABELS = {
    0: "bear",      # low return, high vol
    1: "sideways",  # near-zero return, moderate vol
    2: "bull",      # high return, low-moderate vol
}
```

---

## 10. Backtesting Framework

### 10.1 Framework Architecture

```
┌──────────────────────────────────────────────────────┐
│              BACKTESTING FRAMEWORK                    │
├──────────────┬──────────────┬───────────────────────┤
│  Data Layer  │  Strategy    │  Execution Layer       │
│  - OHLCV     │  - Signals   │  - Order matching      │
│  - Corporate │  - Rules     │  - Slippage model      │
│    Actions   │  - Parameters│  - Cost model          │
│  - Splits    │              │  - Position sizing     │
├──────────────┼──────────────┼───────────────────────┤
│  Risk Layer  │  Analytics   │  Reporting             │
│  - Stop loss │  - Metrics   │  - Equity curve        │
│  - Position  │  - Drawdown  │  - Trade log           │
│    limits    │  - Regime    │  - Summary report      │
└──────────────┴──────────────┴───────────────────────┘
```

### 10.2 Backtest Configuration

```python
@dataclass
class BacktestConfig:
    """Configuration for a backtest run."""
    # Time range
    start_date: str
    end_date: str
    
    # Universe
    tickers: list[str]
    include_delisted: bool = True
    
    # Capital
    initial_capital: float = 100_000_000
    position_size_method: str = "risk_based"  # or "equal_weight", "kelly"
    max_positions: int = 10
    risk_per_trade: float = 0.01
    
    # Costs
    broker_fee_buy: float = 0.0015
    broker_fee_sell: float = 0.0025
    levy: float = 0.00004
    pph: float = 0.001
    slippage_model: str = "square_root"  # or "fixed", "linear"
    
    # Execution
    execution_delay: int = 1  # bars (1 = next day)
    fill_model: str = "close"  # or "open", "vwap", "twap"
    
    # Risk
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.10
    trailing_stop_pct: float = 0.05
    daily_loss_limit: float = 0.02
    
    # Analysis
    benchmark: str = "^JKSE"  # IHSG
    risk_free_rate: float = 0.06
```

---

## 11. Implementasi untuk IDX

### 11.1 Pertimbangan Khusus

| Faktor | Implikasi | Solusi |
|--------|-----------|--------|
| **T+2 settlement** | Cash tidak langsung available | Model settlement delay |
| **Lot size 100** | Quantity harus kelipatan 100 | Round to lot |
| **Auto-reject ±15%** | Price tidak bisa bergerak >15% | Include price limit in simulation |
| **Thin liquidity** | Slippage besar untuk small-cap | Liquidity-aware slippage |
| **Suspend/delisting** | Saham bisa hilang | Include in universe, handle gracefully |
| **Corporate actions** | Split, dividend, rights | Adjust OHLCV |
| **WIB timezone** | Trading hours 09:00-15:50 | Use Asia/Jakarta |

### 11.2 IDX-Specific Backtest Adjustments

```python
def idx_backtest_adjustments(df: pd.DataFrame, ticker: str):
    """Apply IDX-specific adjustments to backtest data."""
    # 1. Adjust for splits
    splits = get_corporate_actions(ticker, action_type="STOCK_SPLIT")
    df = adjust_for_splits(df, splits)
    
    # 2. Mark suspended days
    suspensions = get_suspensions(ticker)
    df["is_suspended"] = df["date"].isin(suspensions)
    
    # 3. Volume filter (skip illiquid days)
    df["is_tradable"] = (df["volume"] > 10000) & ~df["is_suspended"]
    
    # 4. Auto-reject check
    df["daily_return"] = df["close"].pct_change()
    df["is_auto_reject"] = df["daily_return"].abs() > 0.14
    
    return df
```

---

## 12. Checklist Implementasi

### Data
- [ ] Historical OHLCV with corporate action adjustments
- [ ] Include delisted/suspended stocks (no survivorship bias)
- [ ] Correct timezone (Asia/Jakarta)
- [ ] Market calendar (holidays, trading hours)
- [ ] Benchmark data (IHSG/^JKSE)

### Bias Prevention
- [ ] No look-ahead bias (signal shift, execution delay)
- [ ] Survivorship bias (include delisted)
- [ ] Overfitting detection (parameter sensitivity)
- [ ] Data snooping correction (Bonferroni/White's)
- [ ] Out-of-sample testing

### Cost Model
- [ ] Broker fee (buy 0.15%, sell 0.25%)
- [ ] BEI levy (0.004%)
- [ ] PPh final (0.1% sell)
- [ ] Slippage model (square-root)
- [ ] Spread cost estimation

### Validation
- [ ] Walk-forward analysis
- [ ] Monte Carlo simulation (return + trade resampling)
- [ ] Statistical significance test
- [ ] Deflated Sharpe Ratio
- [ ] Regime-aware analysis

### Metrics
- [ ] Total & annualized return
- [ ] Sharpe & Sortino ratio
- [ ] Max drawdown & Calmar ratio
- [ ] Win rate & profit factor
- [ ] Alpha & Beta vs benchmark
- [ ] Information ratio
- [ ] Drawdown duration analysis

### IDX-Specific
- [ ] Lot size rounding (100 shares)
- [ ] Auto-reject simulation (±15%)
- [ ] Suspension handling
- [ ] T+2 settlement modeling
- [ ] Corporate action adjustment
- [ ] Liquidity filter

### Reporting
- [ ] Equity curve chart
- [ ] Drawdown chart
- [ ] Trade log export
- [ ] Monthly returns heatmap
- [ ] Parameter sensitivity table
- [ ] Regime performance breakdown

---

## Referensi

1. López de Prado, M. (2018). "Advances in Financial Machine Learning" — Chapter 11-13
2. Bailey, D. & López de Prado, M. (2012). "The Sharpe Ratio Efficient Frontier"
3. Bailey, D. & López de Prado, M. (2014). "The Deflated Sharpe Ratio"
4. Pardo, R. (2008). "The Evaluation and Optimization of Trading Strategies"
5. `src/trading_system/backtest/` — Backtesting engine
6. `src/trading_system/backtest/engine.py` — Backtest engine
7. `src/trading_system/backtest/strategies.py` — Strategy implementations
8. `src/trading_system/backtest/metrics.py` — Performance metrics
9. `pustaka/08-trading-algoritmik.md` — Trading algoritmik
10. `pustaka/23-machine-learning-trading.md` — ML untuk trading
11. `pustaka/24-market-microstructure-likuiditas.md` — Microstructure & slippage

---

> **Catatan:** Backtest yang baik bukan yang menunjukkan return tertinggi, tetapi yang paling realistis. Jika backtest terlalu bagus untuk jadi kenyataan, kemungkinan besar memang begitu. Selalu gunakan walk-forward + Monte Carlo + realistic costs.
