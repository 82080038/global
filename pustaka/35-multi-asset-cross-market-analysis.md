# Multi-Asset & Cross-Market Analysis

> **Tujuan:** Dokumen ini adalah referensi definitif untuk analisis multi-aset dan cross-market — dari intermarket analysis, correlation dynamics, lead-lag relationships, spillover effects, hingga cross-asset signals — dengan fokus pada pasar modal Indonesia (IDX) dan koneksi ke pasar global.

---

## Daftar Isi

1. [Intermarket Analysis Framework](#1-intermarket-analysis-framework)
2. [Correlation Dynamics](#2-correlation-dynamics)
3. [Lead-Lag Relationships](#3-lead-lag-relationships)
4. [Spillover Effects](#4-spillover-effects)
5. [Cross-Asset Signals](#5-cross-asset-signals)
6. [Global Market Influence on IDX](#6-global-market-influence-on-idx)
7. [Commodity-Equity Linkage](#7-commodity-equity-linkage)
8. [FX-Equity Relationship](#8-fx-equity-relationship)
9. [Sector Rotation Analysis](#9-sector-rotation-analysis)
10. [Implementation](#10-implementation)
11. [Implementasi untuk IDX](#11-implementasi-untuk-idx)
12. [Checklist Implementasi](#12-checklist-implementasi)

---

## 1. Intermarket Analysis Framework

### 1.1 Core Relationships

```
┌─────────────────────────────────────────────────────────────┐
│                  INTERMARKET RELATIONSHIPS                   │
│                                                              │
│  US Bonds ↑ → US Dollar ↑ → EM Currencies ↓ → IDX ↓       │
│                                                              │
│  Commodity ↑ → Commodity Exporters ↑ → IDX (Energy) ↑     │
│                                                              │
│  US Tech ↑ → Global Sentiment ↑ → IDX Foreign Inflow ↑     │
│                                                              │
│  China GDP ↑ → Indonesia Export ↑ → IDX (Basic Mat) ↑     │
│                                                              │
│  USD/IDR ↑ → Foreign Outflow → IDX ↓                       │
│                                                              │
│  BI Rate ↓ → Liquidity ↑ → IDX ↑                           │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Asset Class Matrix

| Asset | Proxy | Influence on IDX | Direction |
|-------|-------|-----------------|-----------|
| **US Equities (S&P 500)** | `^GSPC` | Sentiment | Positive |
| **US Tech (Nasdaq)** | `^IXIC` | Risk appetite | Positive |
| **China Equities** | `000001.SS` | Trade linkage | Positive |
| **US 10Y Yield** | `^TNX` | Risk-off | Negative |
| **USD Index (DXY)** | `DX-Y.NYB` | Capital flow | Negative |
| **Gold** | `GC=F` | Safe haven | Mixed |
| **Crude Oil** | `CL=F` | Energy sector | Positive |
| **Copper** | `HG=F` | Industrial demand | Positive |
| **USD/IDR** | `USDIDR=X` | Foreign flow | Negative |
| **BI Rate** | Macro data | Liquidity | Negative (rate↑ = stock↓) |

### 1.3 Intermarket Analysis Pipeline

```
Global Data → Correlation Analysis → Lead-Lag Detection → Signal Generation
     ↓                ↓                      ↓                    ↓
  S&P 500         Rolling corr           Granger causality     Composite signal
  US 10Y          DCC-GARCH              Cross-correlation     Weight allocation
  USD/IDR         Heatmap                Transfer entropy      Direction prediction
```

---

## 2. Correlation Dynamics

### 2.1 Static Correlation

```python
def compute_correlation_matrix(
    returns: pd.DataFrame,
    method: str = "pearson",
) -> pd.DataFrame:
    """Compute correlation matrix between assets."""
    return returns.corr(method=method)

def correlation_heatmap_data(corr_matrix: pd.DataFrame) -> dict:
    """Prepare correlation data for heatmap visualization."""
    assets = corr_matrix.columns.tolist()
    data = []
    
    for i, asset_i in enumerate(assets):
        for j, asset_j in enumerate(assets):
            data.append({
                "x": asset_i,
                "y": asset_j,
                "value": corr_matrix.loc[asset_i, asset_j],
            })
    
    return {"assets": assets, "data": data}
```

### 2.2 Rolling Correlation

```python
def rolling_correlation(
    returns: pd.DataFrame,
    asset_a: str,
    asset_b: str,
    window: int = 60,
) -> pd.Series:
    """Compute rolling correlation between two assets."""
    return returns[asset_a].rolling(window).corr(returns[asset_b])

def correlation_regime_analysis(
    returns: pd.DataFrame,
    asset_a: str,
    asset_b: str,
    window: int = 60,
) -> dict:
    """Analyze correlation regimes between assets."""
    rolling_corr = rolling_correlation(returns, asset_a, asset_b, window)
    
    # Classify regimes
    high_corr = rolling_corr > 0.7
    moderate_corr = (rolling_corr > 0.3) & (rolling_corr <= 0.7)
    low_corr = (rolling_corr > -0.3) & (rolling_corr <= 0.3)
    negative_corr = rolling_corr <= -0.3
    
    return {
        "mean_correlation": rolling_corr.mean(),
        "current_correlation": rolling_corr.iloc[-1],
        "correlation_std": rolling_corr.std(),
        "high_corr_pct": high_corr.mean() * 100,
        "moderate_corr_pct": moderate_corr.mean() * 100,
        "low_corr_pct": low_corr.mean() * 100,
        "negative_corr_pct": negative_corr.mean() * 100,
        "is_correlation_increasing": rolling_corr.iloc[-1] > rolling_corr.iloc[-20],
    }
```

### 2.3 Dynamic Conditional Correlation (DCC)

```python
def dcc_correlation(returns: pd.DataFrame, window: int = 60):
    """Approximate DCC using exponentially weighted correlation.
    
    Full DCC-GARCH requires arch library; this is a simplified version.
    """
    from pandas import DataFrame
    
    assets = returns.columns
    n = len(assets)
    
    # Exponentially weighted covariance
    ewm_cov = returns.ewm(span=window).cov()
    
    # Convert to correlation
    corr_matrices = {}
    for date in returns.index[window:]:
        if date in ewm_cov.index:
            cov = ewm_cov.loc[date]
            std = np.sqrt(np.diag(cov))
            corr = cov / np.outer(std, std)
            corr_matrices[date] = pd.DataFrame(corr, index=assets, columns=assets)
    
    return corr_matrices
```

### 2.4 Correlation Clustering

```python
def cluster_correlated_assets(corr_matrix: pd.DataFrame, threshold: float = 0.6):
    """Group highly correlated assets using hierarchical clustering."""
    from scipy.cluster.hierarchy import linkage, fcluster
    from scipy.spatial.distance import squareform
    
    # Convert correlation to distance
    dist = 1 - corr_matrix.values
    np.fill_diagonal(dist, 0)
    dist = np.clip(dist, 0, 2)
    
    # Hierarchical clustering
    condensed = squareform(dist)
    Z = linkage(condensed, method='ward')
    clusters = fcluster(Z, t=1 - threshold, criterion='distance')
    
    # Group assets by cluster
    groups = {}
    for asset, cluster_id in zip(corr_matrix.columns, clusters):
        if cluster_id not in groups:
            groups[cluster_id] = []
        groups[cluster_id].append(asset)
    
    return {
        "clusters": groups,
        "n_clusters": len(groups),
        "threshold": threshold,
    }
```

---

## 3. Lead-Lag Relationships

### 3.1 Cross-Correlation Function

```python
def cross_correlation(
    series_a: pd.Series,
    series_b: pd.Series,
    max_lag: int = 20,
) -> dict:
    """Compute cross-correlation at different lags.
    
    Positive lag: A leads B
    Negative lag: B leads A
    """
    correlations = {}
    
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            corr = series_a.shift(lag).corr(series_b)
        else:
            corr = series_a.corr(series_b.shift(-lag))
        
        correlations[lag] = corr
    
    # Find peak correlation
    peak_lag = max(correlations, key=lambda k: abs(correlations[k]))
    
    return {
        "correlations": correlations,
        "peak_lag": peak_lag,
        "peak_correlation": correlations[peak_lag],
        "direction": f"A leads B by {peak_lag} days" if peak_lag > 0 
                     else f"B leads A by {abs(peak_lag)} days" if peak_lag < 0
                     else "No lead-lag",
    }
```

### 3.2 Granger Causality

```python
from statsmodels.tsa.stattools import grangercausalitytests

def granger_causality(
    series_a: pd.Series,
    series_b: pd.Series,
    max_lag: int = 5,
    significance: float = 0.05,
) -> dict:
    """Test if series_a Granger-causes series_b."""
    data = pd.DataFrame({"a": series_a, "b": series_b}).dropna()
    
    results = grangercausalitytests(data[["b", "a"]], maxlag=max_lag, verbose=False)
    
    p_values = {}
    for lag in range(1, max_lag + 1):
        p_values[lag] = results[lag][0]["ssr_ftest"][1]  # p-value
    
    min_p_lag = min(p_values, key=p_values.get)
    is_significant = p_values[min_p_lag] < significance
    
    return {
        "p_values": p_values,
        "min_p_lag": min_p_lag,
        "min_p_value": p_values[min_p_lag],
        "is_significant": is_significant,
        "direction": f"A Granger-causes B (lag={min_p_lag})" if is_significant else "No causality",
    }
```

### 3.3 Lead-Lag Network

```python
def build_lead_lag_network(
    returns: pd.DataFrame,
    max_lag: int = 5,
    significance: float = 0.05,
) -> dict:
    """Build network of lead-lag relationships between all assets."""
    assets = returns.columns
    edges = []
    
    for i, asset_a in enumerate(assets):
        for j, asset_b in enumerate(assets):
            if i >= j:
                continue
            
            # Test A → B
            result_ab = granger_causality(returns[asset_a], returns[asset_b], max_lag, significance)
            if result_ab["is_significant"]:
                edges.append({
                    "source": asset_a,
                    "target": asset_b,
                    "lag": result_ab["min_p_lag"],
                    "p_value": result_ab["min_p_value"],
                })
            
            # Test B → A
            result_ba = granger_causality(returns[asset_b], returns[asset_a], max_lag, significance)
            if result_ba["is_significant"]:
                edges.append({
                    "source": asset_b,
                    "target": asset_a,
                    "lag": result_ba["min_p_lag"],
                    "p_value": result_ba["min_p_value"],
                })
    
    # Identify leaders (many outgoing edges) and followers (many incoming)
    leaders = {}
    followers = {}
    
    for edge in edges:
        leaders[edge["source"]] = leaders.get(edge["source"], 0) + 1
        followers[edge["target"]] = followers.get(edge["target"], 0) + 1
    
    return {
        "edges": edges,
        "n_edges": len(edges),
        "top_leaders": sorted(leaders.items(), key=lambda x: x[1], reverse=True)[:5],
        "top_followers": sorted(followers.items(), key=lambda x: x[1], reverse=True)[:5],
    }
```

---

## 4. Spillover Effects

### 4.1 Volatility Spillover

```python
def volatility_spillover(
    returns: pd.DataFrame,
    window: int = 20,
) -> dict:
    """Measure volatility spillover between assets."""
    volatilities = returns.rolling(window).std()
    
    # Correlation of volatility changes
    vol_changes = volatilities.pct_change()
    vol_corr = vol_changes.corr()
    
    return {
        "volatility_correlation": vol_corr,
        "avg_vol_spillover": vol_corr.mean().mean(),
        "max_vol_spillover": vol_corr.max().max(),
    }
```

### 4.2 Return Spillover (Diebold-Yilmaz)

```python
def diebold_yilmaz_spillover(
    returns: pd.DataFrame,
    lag: int = 2,
    horizon: int = 10,
) -> dict:
    """Diebold-Yilmaz spillover index (simplified)."""
    from statsmodels.tsa.api import VAR
    
    # Fit VAR model
    model = VAR(returns.dropna())
    results = model.fit(lag)
    
    # Forecast error variance decomposition
    fevd = results.fevd(horizon)
    
    # Spillover index
    n = len(returns.columns)
    spillover_table = fevd.decomp[-1]  # last period
    
    # Total spillover
    total_spillover = (spillover_table.sum() - spillover_table.diagonal().sum()) / n * 100
    
    # Directional spillovers
    from_others = spillover_table.sum(axis=1) - spillover_table.diagonal()
    to_others = spillover_table.sum(axis=0) - spillover_table.diagonal()
    
    return {
        "total_spillover_index": total_spillover,
        "from_others": dict(zip(returns.columns, from_others)),
        "to_others": dict(zip(returns.columns, to_others)),
        "net_spillover": dict(zip(returns.columns, to_others - from_others)),
    }
```

---

## 5. Cross-Asset Signals

### 5.1 Signal Types

| Signal | Assets | Logic | IDX Impact |
|--------|--------|-------|------------|
| **Risk-on/Risk-off** | S&P 500, VIX, USD, Gold | VIX↓ + S&P↑ + USD↓ = risk-on | Foreign inflow to IDX |
| **Commodity pulse** | Oil, Copper, Coal | Commodity↑ = energy/basic mat↑ | IDX energy sector↑ |
| **Carry trade** | USD/IDR, BI Rate, US 10Y | Rate differential = carry | IDR strength/weakness |
| **China growth** | Shanghai, Copper, Iron Ore | China↑ = Indonesia export↑ | IDX basic material↑ |
| **Flight to safety** | Gold, US 10Y, VIX | Gold↑ + VIX↑ = risk-off | Foreign outflow from IDX |

### 5.2 Composite Cross-Asset Signal

```python
def cross_asset_signal(global_data: dict) -> dict:
    """Generate composite signal from cross-market data."""
    signals = {}
    
    # 1. Risk-on/Risk-off
    vix = global_data.get("vix_change", 0)
    sp500 = global_data.get("sp500_change", 0)
    usd = global_data.get("dxy_change", 0)
    
    risk_score = 50
    if vix < -0.5 and sp500 > 0.5 and usd < -0.2:
        risk_score = 70  # risk-on
    elif vix > 0.5 and sp500 < -0.5 and usd > 0.2:
        risk_score = 30  # risk-off
    signals["risk_appetite"] = risk_score
    
    # 2. Commodity pulse
    oil = global_data.get("oil_change", 0)
    copper = global_data.get("copper_change", 0)
    coal = global_data.get("coal_change", 0)
    
    commodity_score = 50 + (oil + copper + coal) / 3 * 10
    signals["commodity_pulse"] = max(0, min(100, commodity_score))
    
    # 3. FX pressure
    usd_idr = global_data.get("usd_idr_change", 0)
    fx_score = 50 - usd_idr * 100  # IDR strengthening = positive
    signals["fx_pressure"] = max(0, min(100, fx_score))
    
    # 4. Rate environment
    bi_rate = global_data.get("bi_rate", 6.0)
    us_10y = global_data.get("us_10y", 4.0)
    rate_diff = bi_rate - us_10y
    rate_score = 50 + (rate_diff - 2) * 5  # positive carry = positive
    signals["rate_environment"] = max(0, min(100, rate_score))
    
    # Composite
    weights = {
        "risk_appetite": 0.35,
        "commodity_pulse": 0.25,
        "fx_pressure": 0.25,
        "rate_environment": 0.15,
    }
    
    composite = sum(signals[k] * weights[k] for k in weights)
    
    return {
        "composite_score": composite,
        "label": "bullish" if composite > 55 else "bearish" if composite < 45 else "neutral",
        "components": signals,
        "weights": weights,
    }
```

---

## 6. Global Market Influence on IDX

### 6.1 Key Global Drivers

| Driver | Proxy | Mechanism | Strength |
|--------|-------|-----------|----------|
| **US Market** | S&P 500 | Sentiment, risk appetite | Strong |
| **US Rates** | 10Y Treasury | Capital flow direction | Strong |
| **USD Strength** | DXY | EM capital outflow | Strong |
| **China** | Shanghai Composite | Trade linkage | Moderate |
| **Commodity** | CRB Index | Export revenue | Moderate |
| **Regional** | MSCI Asia ex-Japan | Regional sentiment | Moderate |
| **VIX** | CBOE VIX | Global volatility | Strong |

### 6.2 Overnight Global → IDX Opening

```python
def predict_idx_opening(global_data: dict) -> dict:
    """Predict IDX opening direction from overnight global markets."""
    # US market close (overnight for IDX)
    sp500_change = global_data.get("sp500_change", 0)
    nasdaq_change = global_data.get("nasdaq_change", 0)
    vix_change = global_data.get("vix_change", 0)
    us_10y_change = global_data.get("us_10y_change", 0)
    dxy_change = global_data.get("dxy_change", 0)
    
    # Weighted prediction
    score = (
        sp500_change * 0.30 +
        nasdaq_change * 0.20 +
        vix_change * -0.20 +  # VIX up = negative
        us_10y_change * -0.15 +  # yields up = negative
        dxy_change * -0.15  # USD up = negative
    )
    
    # Scale to -100 to +100
    signal = score * 20
    
    return {
        "predicted_direction": "up" if signal > 5 else "down" if signal < -5 else "flat",
        "signal_strength": abs(signal),
        "score": signal,
        "components": {
            "sp500": sp500_change,
            "nasdaq": nasdaq_change,
            "vix": vix_change,
            "us_10y": us_10y_change,
            "dxy": dxy_change,
        },
        "confidence": min(abs(signal) / 50, 1.0),
    }
```

### 6.3 Foreign Flow Prediction

```python
def predict_foreign_flow(global_data: dict, idx_data: dict) -> dict:
    """Predict foreign flow direction for IDX."""
    # Global factors
    fed_rate = global_data.get("fed_rate", 5.0)
    us_10y = global_data.get("us_10y", 4.0)
    dxy = global_data.get("dxy_change", 0)
    vix = global_data.get("vix_level", 15)
    
    # Local factors
    bi_rate = idx_data.get("bi_rate", 6.0)
    usd_idr = idx_data.get("usd_idr_change", 0)
    idx_valuation = idx_data.get("idx_pe", 15)
    
    # Rate differential (carry trade incentive)
    rate_diff = bi_rate - fed_rate
    
    # Score
    score = 50
    score += (rate_diff - 1) * 5  # positive carry
    score -= dxy * 100  # USD strength = outflow
    score -= (vix - 15) * 2  # high VIX = outflow
    score -= usd_idr * 100  # IDR weakening = outflow
    score -= (idx_valuation - 15) * 2  # expensive = outflow
    
    score = max(0, min(100, score))
    
    return {
        "foreign_flow_score": score,
        "predicted_direction": "net_buy" if score > 55 else "net_sell" if score < 45 else "neutral",
        "rate_differential": rate_diff,
        "confidence": min(abs(score - 50) / 25, 1.0),
    }
```

---

## 7. Commodity-Equity Linkage

### 7.1 IDX Commodity-Linked Sectors

| Sector | Commodities | Key Stocks | Sensitivity |
|--------|------------|------------|-------------|
| **Energy** | Coal, Oil, Gas | ADRO, PTBA, MEDC, BUKA | High |
| **Basic Materials** | Copper, Nickel, Gold, Tin | INCO, ANTM, TINS, MDKA | High |
| **Plantation** | CPO, Rubber | AALI, LSIP, SGRO, SIMP | High |
| **Transport** | Oil (fuel cost) | GIAA, LION, HRTA | Negative (cost) |

### 7.2 Commodity Sensitivity Analysis

```python
def commodity_sensitivity(
    stock_returns: pd.Series,
    commodity_returns: pd.Series,
    window: int = 60,
) -> dict:
    """Analyze stock sensitivity to commodity price changes."""
    rolling_beta = stock_returns.rolling(window).cov(commodity_returns) / \
                   commodity_returns.rolling(window).var()
    
    return {
        "current_beta": rolling_beta.iloc[-1],
        "avg_beta": rolling_beta.mean(),
        "beta_std": rolling_beta.std(),
        "beta_trend": "increasing" if rolling_beta.iloc[-1] > rolling_beta.iloc[-20] else "decreasing",
        "sensitivity_label": (
            "high_positive" if rolling_beta.iloc[-1] > 0.5 else
            "moderate_positive" if rolling_beta.iloc[-1] > 0.2 else
            "low" if rolling_beta.iloc[-1] > -0.2 else
            "moderate_negative" if rolling_beta.iloc[-1] > -0.5 else
            "high_negative"
        ),
    }
```

---

## 8. FX-Equity Relationship

### 8.1 USD/IDR Impact

```python
def fx_equity_analysis(
    idx_returns: pd.Series,
    usd_idr_returns: pd.Series,
    window: int = 60,
) -> dict:
    """Analyze USD/IDR relationship with IDX."""
    rolling_corr = idx_returns.rolling(window).corr(usd_idr_returns)
    
    return {
        "current_correlation": rolling_corr.iloc[-1],
        "avg_correlation": rolling_corr.mean(),
        "interpretation": (
            "USD/IDR up → IDX down (typical)" if rolling_corr.iloc[-1] < -0.2 else
            "USD/IDR up → IDX up (atypical)" if rolling_corr.iloc[-1] > 0.2 else
            "Weak FX-equity relationship"
        ),
        "correlation_stability": "stable" if rolling_corr.std() < 0.15 else "unstable",
    }
```

### 8.2 Foreign Flow → FX → Equity Loop

```
Foreign Net Sell → IDR Depreciation → Higher Import Costs → 
  Corporate Earnings ↓ → IDX ↓ → More Foreign Sell → Loop
```

---

## 9. Sector Rotation Analysis

### 9.1 Sector Rotation Model

```python
SECTOR_ROTATION = {
    "early_bull": ["IDXFINANCE", "IDXINDUST", "IDXCYCLIC"],
    "mid_bull": ["IDXNONCYC", "IDXTECHNO", "IDXHEALTH"],
    "late_bull": ["IDXENERGY", "IDXBASIC", "IDXTRANS"],
    "early_bear": ["IDXNONCYC", "IDXHEALTH", "IDXFINANCE"],
    "mid_bear": ["IDXINFRA", "IDXPROPERT"],
    "late_bear": ["IDXENERGY", "IDXBASIC", "IDXCYCLIC"],
}

def detect_sector_rotation(
    sector_returns: pd.DataFrame,
    market_regime: str,
) -> dict:
    """Detect current sector rotation phase."""
    # Recent sector performance
    recent = sector_returns.tail(20).mean().sort_values(ascending=False)
    
    # Expected leaders for current regime
    expected_leaders = SECTOR_ROTATION.get(market_regime, [])
    
    # Check alignment
    actual_leaders = recent.head(3).index.tolist()
    alignment = len(set(actual_leaders) & set(expected_leaders)) / 3
    
    return {
        "current_regime": market_regime,
        "expected_leaders": expected_leaders,
        "actual_leaders": actual_leaders,
        "alignment_score": alignment,
        "sector_momentum": recent.to_dict(),
        "rotation_signal": "confirmed" if alignment > 0.6 else "transitioning" if alignment > 0.3 else "divergent",
    }
```

---

## 10. Implementation

### 10.1 Relationship Engine Integration

```python
class RelationshipEngine:
    """Cross-market relationship analysis engine."""
    
    def analyze(self, ticker: str) -> dict:
        """Compute relationship score for a ticker."""
        scores = {}
        
        # 1. Market correlation (vs IHSG)
        market_corr = self._market_correlation(ticker)
        scores["market_beta"] = market_corr["beta"]
        
        # 2. Sector correlation
        sector_corr = self._sector_correlation(ticker)
        scores["sector_alignment"] = sector_corr["alignment"]
        
        # 3. Global drivers
        global_signal = cross_asset_signal(self.global_data)
        scores["global_signal"] = global_signal["composite_score"]
        
        # 4. Commodity linkage
        commodity = self._commodity_linkage(ticker)
        scores["commodity_sensitivity"] = commodity["score"]
        
        # 5. FX sensitivity
        fx = self._fx_sensitivity(ticker)
        scores["fx_sensitivity"] = fx["score"]
        
        # Aggregate
        weights = {
            "market_beta": 0.25,
            "sector_alignment": 0.25,
            "global_signal": 0.25,
            "commodity_sensitivity": 0.15,
            "fx_sensitivity": 0.10,
        }
        
        total = sum(scores[k] * weights[k] for k in weights)
        
        return {
            "ticker": ticker,
            "relationship_score": total,
            "components": scores,
            "weights": weights,
        }
```

### 10.2 Decision Engine Weight

```python
# Relationship analysis has 10% weight in Decision Engine
DECISION_WEIGHTS = {
    "technical": 0.20,
    "fundamental": 0.25,
    "macro": 0.15,
    "global": 0.15,
    "relationship": 0.10,  # ← from RelationshipEngine
    "sentiment": 0.15,
}
```

---

## 11. Implementasi untuk IDX

### 11.1 IDX-Specific Cross-Market

| Relationship | Strength | Notes |
|--------------|----------|-------|
| **S&P 500 → IHSG** | Moderate (corr ~0.4) | Sentiment channel |
| **USD/IDR → IHSG** | Strong (corr ~-0.5) | Foreign flow channel |
| **Coal → ADRO/PTBA** | Very strong (corr ~0.7) | Direct revenue |
| **CPO → AALI/SGRO** | Strong (corr ~0.6) | Direct revenue |
| **BI Rate → IDX Finance** | Moderate | Net interest margin |
| **China → IDX Basic Mat** | Moderate | Export demand |
| **VIX → Foreign Flow** | Strong | Risk-off = outflow |

### 11.2 Data Requirements

```python
GLOBAL_DATA_SOURCES = {
    "US Market": {"tickers": ["^GSPC", "^IXIC", "^DJI"], "source": "yahoo"},
    "US Rates": {"tickers": ["^TNX"], "source": "yahoo"},
    "Volatility": {"tickers": ["^VIX"], "source": "yahoo"},
    "USD Index": {"tickers": ["DX-Y.NYB"], "source": "yahoo"},
    "Commodities": {"tickers": ["CL=F", "HG=F", "GC=F"], "source": "yahoo"},
    "Asia": {"tickers": ["^N225", "^HSI", "000001.SS"], "source": "yahoo"},
    "FX": {"tickers": ["USDIDR=X", "USDCNY=X"], "source": "yahoo"},
}
```

---

## 12. Checklist Implementasi

### Correlation
- [ ] Static correlation matrix computation
- [ ] Rolling correlation (60-day window)
- [ ] Correlation regime analysis
- [ ] Correlation clustering
- [ ] Correlation heatmap visualization

### Lead-Lag
- [ ] Cross-correlation function
- [ ] Granger causality test
- [ ] Lead-lag network construction
- [ ] Leader/follower identification

### Spillover
- [ ] Volatility spillover analysis
- [ ] Return spillover (Diebold-Yilmaz)
- [ ] Directional spillover (from/to others)

### Cross-Asset Signals
- [ ] Risk-on/risk-off signal
- [ ] Commodity pulse signal
- [ ] FX pressure signal
- [ ] Rate environment signal
- [ ] Composite cross-asset score

### Global → IDX
- [ ] Overnight global → IDX opening prediction
- [ ] Foreign flow prediction model
- [ ] Global driver correlation tracking

### Commodity Linkage
- [ ] Commodity sensitivity per stock
- [ ] Sector-commodity mapping
- [ ] Rolling beta to commodity

### FX
- [ ] USD/IDR → IDX correlation
- [ ] Foreign flow → FX → equity loop model
- [ ] FX-adjusted returns

### Sector Rotation
- [ ] Sector performance ranking
- [ ] Regime-based expected leaders
- [ ] Rotation detection signal

### Integration
- [ ] RelationshipEngine with weighted aggregation
- [ ] Integration with Decision Engine (10% weight)
- [ ] Relationship matrix storage
- [ ] Real-time global data fetching

---

## Referensi

1. `src/trading_system/analysis/relationship.py` — Relationship engine
2. `src/trading_system/analysis/cross_asset.py` — Cross-asset analysis
3. `src/trading_system/analysis/lead_lag.py` — Lead-lag analysis
4. `src/trading_system/analysis/global_market.py` — Global market engine
5. `src/trading_system/data/acquisition.py` — Global data fetching
6. `pustaka/03-pasar-modal-global.md` — Global market overview
7. `pustaka/07-manajemen-risiko.md` — Risk & correlation
8. `pustaka/21-portfolio-optimization-construction.md` — Portfolio optimization
9. Diebold, F. & Yilmaz, K. (2012). "Better to Give than to Receive"
10. López de Prado, M. (2018). "Advances in Financial Machine Learning"

---

## 12. Implementasi: World Monitor & Country Instability Index (CII)

> **Sumber:** `src/trading_system/analysis/world_monitor.py` (336 baris)

Sistem `trading-system` mengimplementasikan dua konsep dari worldmonitor (TypeScript, reverse-engineered ke Python):

### 12.1 7-Signal Market Composite

Deteksi pola cross-source dari news + market data streams:

| Signal | Deskripsi |
|--------|-----------|
| **Convergence** | Multiple sources mengkonfirmasi tren yang sama |
| **Velocity** | Kecepatan perubahan sentimen/harga |
| **Divergence** | Source conflict (mis. harga naik tapi news negatif) |
| **Sector cascade** | Efek domino antar sektor |
| **Volume anomaly** | Volume tidak wajar vs baseline |
| **Sentiment shift** | Perubahan sentimen tajam |
| **Correlation breakdown** | Korelasi historis putus |

### 12.2 Country Instability Index (CII)

4-component geopolitical risk score per negara:

| Komponen | Kode | Deskripsi |
|----------|------|-----------|
| **Unrest** | U | Kerusuhan/protes sipil |
| **Conflict** | C | Konflik bersenjata/sengketa |
| **Security** | S | Tingkat keamanan |
| **Information** | I | Akses informasi/transparansi |

Formula: `CII = (U + C + S + I) × event_multiplier + baseline_risk`

### 12.3 Country Weights (sample)

| Negara | Baseline Risk | Event Multiplier |
|--------|---------------|-------------------|
| US | 5 | 0.3 |
| CN | 25 | 2.5 |
| ID | 15 | 0.8 |
| JP | 5 | 0.5 |
| RU | 35 | 2.0 |

### 12.4 Integrasi

- **Global market engine:** CII sebagai input untuk risk premium
- **Decision engine:** CII tinggi → kurangi exposure ke pasar terkait
- **Alert system:** CII spike → notifikasi geopolitical risk warning

---

> **Catatan:** Pasar tidak bergerak dalam isolasi. IDX sangat dipengaruhi oleh global market, commodity prices, dan USD/IDR. Sistem trading yang mengabaikan intermarket relationships akan kehilangan konteks penting dan membuat keputusan yang suboptimal. Implementasi: `src/trading_system/analysis/world_monitor.py`.
