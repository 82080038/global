# Arsitektur Sistem Trading Profesional — Kerangka Dasar

## 1. Visi dan Prinsip Arsitektur

Sistem ini dirancang bukan sebagai **pembuat sinyal sederhana**, melainkan sebagai **sistem operasi pengambilan keputusan investasi** yang terstruktur, dapat diaudit, dan tumbuh secara bertahap.

### Prinsip Inti

- **Data First:** Keputusan hanya sekuat data yang masuk.
- **Backtestable First:** Setiap hipotesis strategi harus dapat diuji secara historis.
- **Modular & Decoupled:** Setiap engine dapat dikembangkan, diuji, dan diganti secara independen.
- **Explainable:** Setiap rekomendasi harus dapat dijelaskan faktor apa saja yang memengaruhinya.
- **Risk-Aware:** Tanpa pengelolaan risiko, sistem tidak boleh menghasilkan sinyal.
- **Continuous Learning:** AI tidak menggantikan keputusan, melainkan membantu menemukan pola dan bobot faktor.

---

## 2. Layered Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         PRESENTATION & COMMAND LAYER                          │
│  Dashboard, Alerts, Report Generator, Strategy Editor, Audit Logs            │
├──────────────────────────────────────────────────────────────────────────────┤
│                         DECISION & LEARNING LAYER                             │
│  Decision Engine  →  AI Learning Engine  →  Explainable AI Engine              │
├──────────────────────────────────────────────────────────────────────────────┤
│                         RISK & PORTFOLIO LAYER                                │
│  Risk Engine  +  Portfolio Engine  +  Execution Engine                       │
├──────────────────────────────────────────────────────────────────────────────┤
│                         ANALYSIS LAYER                                        │
│  Fundamental │ Technical │ Macro │ Global │ Sentiment │ Corporate Action     │
├──────────────────────────────────────────────────────────────────────────────┤
│                         RELATIONSHIP & INTELLIGENCE LAYER                     │
│  Market Relationship Engine  +  Cross-Asset Correlation Engine                 │
├──────────────────────────────────────────────────────────────────────────────┤
│                         DATA LAYER                                            │
│  Acquisition → Validation → Storage → Catalog → API / Event Bus                │
├──────────────────────────────────────────────────────────────────────────────┤
│                         INFRASTRUCTURE LAYER                                  │
│  Scheduler, Monitoring 24/7, Logging, Backtesting, Paper Trading, Deployment    │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Modul-Modul Inti

### 3.1 Data Layer

#### 3.1.1 Data Acquisition Engine

**Tujuan:** Mengumpulkan data dari berbagai sumber secara otomatis, terjadwal, dan terverifikasi.

| Kategori | Data | Sumber Contoh |
|----------|------|---------------|
| Saham Indonesia | Harga, volume, kliring, laporan keuangan | IDX, BEI, Bloomberg, Refinitiv |
| Saham Global | Bursa AS, Tiongkok, Eropa, Asia | Yahoo Finance, Alpha Vantage, IEX |
| Indeks | IHSG, LQ45, S&P 500, Nasdaq, Hang Seng, dll. | Bursa efek masing-masing |
| Forex & Valas | USD/IDR, DXY, CNY/USD, JPY/USD | OANDA, ForexFactory |
| Obligasi & Suku Bunga | SBN, US Treasury, BI Rate, Fed Rate | Bank Indonesia, FRED, Bloomberg |
| Komoditas | Minyak, emas, batu bara, CPO, nikel | Investing.com, World Bank, EIA |
| Makroekonomi | Inflasi, GDP, pengangguran, PDB | BPS, BI, FRED, TradingEconomics |
| Laporan Keuangan | Neraca, laba rugi, arus kas, rasio | Emiten, BEI, third-party data |
| Kalender Ekonomi | Rilis data makro, event BI/FOMC | ForexFactory, TradingEconomics |
| Berita & Sentimen | Headline berita, laporan analis | NewsAPI, Google News, RSS, X/Twitter |

**Komponen Teknis:**

- Adapters/Connectors untuk setiap sumber API
- Rate limiter dan retry mechanism
- Normalisasi skema data (OHLCV standard, ticker mapping)
- Metadata tracking: `source`, `last_updated`, `frequency`, `status`

**Input:**

- Konfigurasi sumber data (`source_config.yaml`): endpoint, API key, ticker list, frekuensi polling
- Jadwal dari Scheduler (Infrastructure Layer) — cron/interval per jenis data

**Output:**

- Event `data.raw.<kategori>` (mis. `data.raw.ohlcv`, `data.raw.fundamental`, `data.raw.news`) berisi payload mentah + metadata
- Raw data terpasang di staging area (`raw_zone` pada Data Storage)

**Fungsi Utama (kontrak fungsi):**

| Fungsi | Input | Output |
|--------|-------|--------|
| `fetch(source, ticker, range)` | source id, ticker/kode, rentang tanggal | payload mentah + status HTTP |
| `normalize(payload, schema)` | payload mentah, skema target | record ternormalisasi (lihat §4 Kontrak Data) |
| `publish(record)` | record ternormalisasi | event ke Event Bus + tulis ke `raw_zone` |
| `track_metadata(source, status)` | source id, hasil fetch | update tabel `source_health` |

**Terhubung dengan (Dependencies):**

- **Downstream:** Data Quality Validation Engine (konsumen utama seluruh output)
- **Upstream:** Scheduler (Infrastructure Layer) yang memicu proses fetch
- **Event Bus:** mempublikasikan ke topic `data.raw.*`

---

#### 3.1.2 Data Quality Validation Engine

**Tujuan:** Menjamin data yang masuk ke sistem bersih, konsisten, dan dapat dipercaya.

**Jenis Validasi:**

1. **Completeness Check**
   - Missing values per kolom dan per periode
   - Gap pada data harian/mingguan/bulanan
   - Data sources yang mati atau lambat

2. **Plausibility Check**
   - Harga negatif atau nol
   - Volume yang tiba-tiba melonjak tanpa alasan
   - Candlestick dengan `low > high` atau `close` di luar range
   - Rasio fundamental yang tidak realistis (misal PER > 10.000)

3. **Cross-Source Validation**
   - Bandingkan harga dari dua sumber berbeda
   - Deteksi outlier berdasarkan deviasi antar-sumber

4. **Reconciliation Engine**
   - Tracking revisi data makro
   - Versioning data historis
   - Audit log perubahan nilai

**Output:**

- `data_quality_score`
- Daftar anomali dan tindakan otomatis (interpolasi, flagging, pause sinyal)

**Input:**

- Event `data.raw.*` dari Data Acquisition Engine
- Referensi historis dari Data Storage untuk cross-check dan reconciliation

**Fungsi Utama:**

| Fungsi | Input | Output |
|--------|-------|--------|
| `check_completeness(record_set)` | kumpulan record per periode | daftar gap/missing |
| `check_plausibility(record)` | satu record OHLCV/fundamental | flag anomali + severity |
| `cross_validate(record, alt_sources)` | record + record sumber lain | deviation score |
| `reconcile(record, historical_version)` | record baru vs versi lama | versi baru + audit log entry |
| `score(record_set)` | hasil semua check di atas | `data_quality_score` (0–100) |

**Terhubung dengan (Dependencies):**

- **Upstream:** Data Acquisition Engine (`data.raw.*`)
- **Downstream:** Data Storage (`clean_zone`), seluruh Analysis Layer, Monitoring Engine (menerima alert jika `data_quality_score` di bawah threshold)
- **Event Bus:** konsumsi `data.raw.*`, publikasi `data.clean.*` dan `data.quality.alert`

---

### 3.2 Intelligence Layer

#### 3.2.1 Market Relationship Engine

**Tujuan:** Menghitung pengaruh antarpasar secara kuantitatif dan dinamis.

**Contoh Relasi yang Diukur:**

- Pengaruh pergerakan **S&P 500 / Nasdaq** terhadap **IHSG** keesokan harinya
- Pengaruh **CNH/CNY** dan bursa **Hang Seng / Shanghai** terhadap sektor tertentu di Indonesia
- Pengaruh **harga minyak / batu bara** terhadap saham energi dan tambang
- Pengaruh **DXY (USD Index)** terhadap USD/IDR dan aset berisiko RI
- Pengaruh **yield US 10Y** terhadap pasar obligasi Indonesia
- Pengaruh **pergerakan sektor global** (misal: semiconductor, banking) terhadap sektor lokal

**Metode:**

- Rolling correlation dan lag analysis
- Granger causality (opsional)
- Regression dengan rolling window
- Regime detection untuk mengidentifikasi perubahan hubungan

**Input:**

- Data harga/indeks dari `data.clean.ohlcv` (saham lokal, global, komoditas, forex)
- Macro regime label dari Macro Economic Engine (untuk conditioning relasi per regime)

**Output:**

- `relationship_matrix` (pasangan aset → koefisien korelasi/lag/beta, per rolling window)
- `influence_score` per ticker/sektor (seberapa besar dipengaruhi pasar global tertentu)
- Event `analysis.relationship.updated`

**Fungsi Utama:**

| Fungsi | Input | Output |
|--------|-------|--------|
| `rolling_correlation(series_a, series_b, window)` | 2 seri waktu, ukuran window | koefisien korelasi bergulir |
| `lag_analysis(series_a, series_b, max_lag)` | 2 seri waktu, lag maksimum | lag optimal + kekuatan hubungan |
| `granger_test(series_a, series_b)` | 2 seri waktu | p-value kausalitas |
| `detect_regime_shift(relationship_series)` | seri koefisien historis | titik perubahan regime hubungan |

**Terhubung dengan (Dependencies):**

- **Upstream:** Data Storage (`data.clean.*`), Macro Economic Engine, Global Market Engine
- **Downstream:** Decision Engine (sebagai salah satu skor input), Explainable AI Engine (untuk narasi "pengaruh pasar X")

---

### 3.3 Analysis Layer

#### 3.3.1 Fundamental Analysis Engine

**Tujuan:** Menilai kesehatan dan valuasi perusahaan berdasarkan laporan keuangan.

**Rasio & Metrik Utama:**

| Kategori | Rasio/Metrik |
|----------|--------------|
| Valuasi | PER, PBV, EV/EBITDA, Dividend Yield |
| Profitabilitas | ROE, ROA, ROIC, Gross Margin, Operating Margin, Net Margin |
| Pertumbuhan | EPS Growth, Revenue Growth, EBITDA Growth |
| Leverage & Solvabilitas | DER, Interest Coverage, Debt to Asset |
| Likuiditas | Current Ratio, Quick Ratio |
| Efisiensi | Asset Turnover, Inventory Turnover |
| Arus Kas | Operating Cash Flow, Free Cash Flow, FCF Yield |
| Kualitas Laba | Cash Conversion Cycle, Earnings Quality Ratio |

**Fitur Tambahan:**

- Rekonsiliasi data kuartalan dan tahunan
- Handling revisi laporan keuangan
- Proyeksi dasar dari tren historis (opsional, dengan uncertainty band)
- Sektor-relative ranking

**Input:**

- Event `data.clean.fundamental` (laporan keuangan ternormalisasi per emiten per periode)
- Data sektor/klasifikasi industri (IDX Sector Classification) untuk ranking relatif

**Output:**

- `fundamental_score` per ticker (0–100) beserta breakdown per rasio
- Event `analysis.fundamental.score`

**Fungsi Utama:**

| Fungsi | Input | Output |
|--------|-------|--------|
| `compute_ratios(financial_statement)` | laporan keuangan 1 periode | dict rasio (PER, ROE, DER, dst.) |
| `sector_rank(ratios, sector_peers)` | rasio ticker + rasio sektor | persentil relatif sektor |
| `score(ratios, sector_rank, weights)` | rasio + ranking + bobot faktor | `fundamental_score` |
| `project_trend(historical_ratios)` | rasio historis | proyeksi + uncertainty band |

**Terhubung dengan (Dependencies):**

- **Upstream:** Data Quality Validation Engine, Corporate Action Engine (adjustment untuk aksi korporasi)
- **Downstream:** Decision Engine, Explainable AI Engine, AI Learning Engine (sebagai fitur/feature)

---

#### 3.3.2 Technical Analysis Engine

**Tujuan:** Menganalisis perilaku harga dan volume secara kuantitatif, bukan hanya mengandalkan indikator populer.

**Komponen:**

1. **Trend Analysis**
   - Moving averages, ADX, trend strength
   - Trend regime classification (uptrend/downtrend/sideways)

2. **Momentum**
   - RSI, MACD, Stochastic, Williams %R, ROC
   - Momentum divergence detection

3. **Volatility**
   - ATR, Bollinger Bands, Keltner Channels
   - Volatility regime detection

4. **Support & Resistance**
   - Pivot points, swing highs/lows, volume profile levels
   - Order block dan supply/demand zones (deteksi sederhana)

5. **Market Breadth**
   - Advance-decline ratio, new highs/new lows
   - Breadth indicators untuk IHSG / sektor

6. **Volume Profile**
   - Volume by price level
   - Point of Control (POC), Value Area High/Low
   - Volume anomaly detection

**Input:**

- Event `data.clean.ohlcv` (harga & volume harian/intraday)

**Output:**

- `technical_score` per ticker (0–100) beserta breakdown per komponen (trend, momentum, volatility, breadth, volume)
- `regime_label` teknikal (uptrend/downtrend/sideways, high-vol/low-vol)
- Event `analysis.technical.score`

**Fungsi Utama:**

| Fungsi | Input | Output |
|--------|-------|--------|
| `compute_indicators(ohlcv_series)` | seri OHLCV | dict indikator (MA, RSI, MACD, ATR, dst.) |
| `classify_trend_regime(indicators)` | indikator tren | label regime |
| `detect_divergence(price, momentum_indicator)` | harga + indikator momentum | flag divergence |
| `volume_profile(ohlcv_series)` | seri OHLCV | POC, VAH, VAL |
| `score(indicators, regime, volume_profile)` | semua di atas | `technical_score` |

**Terhubung dengan (Dependencies):**

- **Upstream:** Data Quality Validation Engine
- **Downstream:** Decision Engine, Explainable AI Engine, AI Learning Engine, Backtesting Engine (untuk sinyal historis)

---

#### 3.3.3 Macro Economic Engine

**Tujuan:** Memantau dan mengukur dampak kondisi makroekonomi terhadap pasar.

**Data yang Diproses:**

- Suku bunga: BI Rate, Fed Funds Rate, suku bunga deposito
- Inflasi: CPI Indonesia, CPI AS, core inflation
- PDB / GDP: Indonesia, AS, Tiongkok, dunia
- Pengangguran: TPT Indonesia, non-farm payrolls AS
- Obligasi: yield SBN 10Y, US Treasury 10Y, yield curve
- Kredit dan likuiditas: pertumbuhan kredit, M2, foreign reserves
- Nilai tukar: USD/IDR, trade balance, current account

**Output:**

- Macro regime classification (easing, tightening, growth, slowdown)
- Yield curve analysis (normal, inverted, flattening)
- Macro surprise index (actual vs consensus)

**Input:**

- Event `data.clean.macro` (rilis data makro Indonesia & global, termasuk konsensus/forecast bila tersedia)
- Kalender ekonomi (`data.clean.calendar`) untuk mapping rilis vs ekspektasi

**Fungsi Utama:**

| Fungsi | Input | Output |
|--------|-------|--------|
| `classify_regime(rate_series, inflation_series, gdp_series)` | seri suku bunga, inflasi, PDB | label regime makro |
| `analyze_yield_curve(yield_points)` | yield berbagai tenor | bentuk kurva (normal/inverted/flat) |
| `surprise_index(actual, consensus)` | data aktual vs konsensus | skor surprise (+/-) |

**Output tambahan:** Event `analysis.macro.regime`

**Terhubung dengan (Dependencies):**

- **Upstream:** Data Quality Validation Engine
- **Downstream:** Decision Engine (regime filter), Market Relationship Engine (conditioning), Risk Engine (macro-based risk flag)

---

#### 3.3.4 Global Market Engine

**Tujuan:** Memantau bursa utama dunia dan mengukur dampaknya ke Indonesia.

**Bursa & Indeks yang Dipantau:**

| Wilayah | Indeks |
|---------|--------|
| Amerika | S&P 500, Nasdaq, Dow Jones, Russell 2000, VIX |
| Tiongkok | Shanghai Composite, Hang Seng, CSI 300 |
| Asia | Nikkei 225, KOSPI, STI, SET |
| Eropa | DAX, FTSE 100, CAC 40, Euro Stoxx 50 |
| Komoditas | Oil, Gold, Coal, CPO, Nickel, Copper |
| Forex | DXY, USD/IDR, CNY/USD, JPY/USD |

**Output:**

- Global risk appetite index
- Regional market stress score
- Correlation matrix antara IHSG dan pasar global
- Overnight gap prediction (preliminary)

**Input:**

- Event `data.clean.ohlcv` untuk indeks global, forex, komoditas

**Fungsi Utama:**

| Fungsi | Input | Output |
|--------|-------|--------|
| `risk_appetite_index(vix, credit_spread, fx_volatility)` | indikator risk-on/off global | skor risk appetite |
| `stress_score(regional_indices)` | indeks per wilayah | skor stres regional |
| `predict_overnight_gap(us_close, futures)` | penutupan AS + futures | estimasi gap pembukaan IHSG |

**Output tambahan:** Event `analysis.global.score`

**Terhubung dengan (Dependencies):**

- **Upstream:** Data Quality Validation Engine
- **Downstream:** Decision Engine, Market Relationship Engine (input korelasi), Explainable AI Engine

---

#### 3.3.5 News & Sentiment Engine

**Tujuan:** Bukan sekadar membaca berita, tapi mengelompokkan dan mengukur sentimennya.

**Tahapan:**

1. **News Acquisition:** RSS, API berita, X/Twitter, laporan analis, keterbukaan BEI
2. **Document Classification:**
   - Topik: makro, politik, perusahaan, sektor, global
   - Entitas: emiten, negara, sektor, komoditas
3. **Sentiment Analysis:**
   - Lexicon-based dan model-based sentiment scoring
   - Entity-level sentiment (bukan hanya dokumen-level)
4. **Impact Scoring:**
   - Berita penting vs berita biasa (dampak harga historis)
   - Sentiment momentum dan sentiment divergence
5. **Event Clustering:**
   - Kelompokkan berita serupa
   - Deteksi narasi dominan pasar

**Input:**

- Event `data.raw.news` (headline, isi, sumber, timestamp)

**Output:**

- `sentiment_score` per entitas (ticker/sektor/negara), per rentang waktu
- `event_cluster` (narasi dominan + daftar berita anggota)
- Event `analysis.sentiment.score`

**Fungsi Utama:**

| Fungsi | Input | Output |
|--------|-------|--------|
| `classify_document(text)` | teks berita | topik + entitas terdeteksi |
| `score_sentiment(text, entity)` | teks + entitas target | skor sentimen (-1..1) |
| `impact_score(sentiment_score, historical_price_reaction)` | skor sentimen + histori reaksi harga | bobot dampak |
| `cluster_events(document_set)` | kumpulan dokumen dalam window waktu | daftar cluster/narasi |

**Terhubung dengan (Dependencies):**

- **Upstream:** Data Acquisition Engine (`data.raw.news`)
- **Downstream:** Decision Engine, Explainable AI Engine, AI Learning Engine

---

#### 3.3.6 Corporate Action Engine

**Tujuan:** Memantau aksi korporasi yang memengaruhi valuasi, harga, dan posisi.

**Aksi Korporasi yang Dilacak:**

- Dividen (interim, final)
- Stock split & reverse stock split
- Rights issue
- Share buyback
- Akuisisi, merger, divestasi
- RUPST / RUPSLB
- Private placement
- Delisting / IPO

**Output:**

- Kalender aksi korporasi
- Adjustment factor untuk perhitungan harga adjusted
- Event study: dampak historis aksi korporasi terhadap harga

**Input:**

- Event `data.raw.corporate_action` (pengumuman resmi BEI/emiten)

**Fungsi Utama:**

| Fungsi | Input | Output |
|--------|-------|--------|
| `parse_action(announcement)` | pengumuman mentah | record aksi korporasi terstruktur |
| `compute_adjustment_factor(action, price_series)` | aksi + harga sekitar tanggal aksi | faktor penyesuaian harga |
| `apply_adjustment(price_series, factor)` | harga mentah + faktor | harga adjusted |
| `event_study(action_type, price_series)` | jenis aksi + histori harga sejenis | rata-rata dampak historis |

**Output tambahan:** Event `analysis.corporate_action.updated`

**Terhubung dengan (Dependencies):**

- **Upstream:** Data Acquisition Engine
- **Downstream:** Fundamental Analysis Engine (adjusted ratio), Technical Analysis Engine (adjusted price), Portfolio Engine (dividen/rights untuk cash flow)

---

### 3.4 Risk & Portfolio Layer

#### 3.4.1 Risk Engine

**Tujuan:** Melindungi modal sebelum sistem memberikan sinyal.

**Komponen:**

1. **Position Sizing**
   - Fixed fraction, Kelly fraction (conservative), volatility targeting
   - Maximum position size per saham dan per sektor

2. **Stop Loss & Take Profit**
   - Initial stop loss (technical-based, ATR-based, fixed %)
   - Trailing stop
   - Time-based exit

3. **Drawdown Control**
   - Maximum portfolio drawdown limit
   - Circuit breaker otomatis saat drawdown melewati threshold

4. **Diversification Control**
   - Exposure limit per sektor, per kapitalisasi, per tema
   - Geographic exposure (untuk ETF/global assets)

5. **Correlation & Tail Risk**
   - Rolling correlation antar posisi
   - Value-at-Risk (VaR) dan Expected Shortfall (CVaR)
   - Stress testing dengan skenario historis

6. **Liquidity Risk**
   - Average daily volume check sebelum entry
   - Slippage estimation berdasarkan order size

**Input:**

- Kandidat sinyal mentah dari Analysis Layer (skor fundamental/teknikal/makro/global/sentimen)
- Posisi portofolio berjalan dari Portfolio Engine
- Data volatilitas & volume dari Technical Analysis Engine

**Output:**

- `position_size`, `stop_loss`, `take_profit` per kandidat
- `risk_flags` (mis. `LIQUIDITY_LOW`, `DRAWDOWN_BREACH`, `CORRELATION_HIGH`)
- Event `risk.assessment.completed`

**Fungsi Utama:**

| Fungsi | Input | Output |
|--------|-------|--------|
| `position_size(capital, volatility, method)` | modal, volatilitas, metode (Kelly/fixed/vol-target) | ukuran posisi |
| `initial_stop_loss(entry_price, atr, method)` | harga entry, ATR, metode | level stop loss |
| `check_drawdown(portfolio_equity_curve)` | equity curve berjalan | status circuit breaker |
| `check_liquidity(avg_daily_volume, order_size)` | volume rata-rata, ukuran order | flag likuiditas + estimasi slippage |
| `compute_var(portfolio_returns, confidence)` | return historis portofolio | VaR/CVaR |

**Terhubung dengan (Dependencies):**

- **Upstream:** Decision Engine (kandidat sinyal), Portfolio Engine (posisi berjalan), Technical Analysis Engine (volatilitas/volume)
- **Downstream:** Decision Engine (hasil risk filter dikirim balik sebelum finalisasi rekomendasi), Portfolio Engine (limit eksposur)

---

#### 3.4.2 Portfolio Engine

**Tujuan:** Mengelola alokasi modal dan rebalancing secara sistematis.

**Fitur:**

- Target allocation per sektor / tema / strategi
- Rebalancing rules (threshold-based, calendar-based)
- Cash buffer management
- Strategy-level capital allocation
- Performance attribution (Brinson model / factor-based)
- Tax-aware rebalancing (untuk aspek pajak Indonesia)

**Input:**

- `recommendation` terverifikasi dari Decision Engine (sudah lolos Risk Engine)
- Posisi & cash balance saat ini (dari Data Storage tabel `positions`)
- Adjustment factor aksi korporasi (dividen/rights) dari Corporate Action Engine

**Output:**

- `target_allocation` per sektor/tema/strategi
- `rebalance_order_list` (daftar order yang perlu dieksekusi untuk mencapai target)
- Event `portfolio.rebalance.generated`

**Fungsi Utama:**

| Fungsi | Input | Output |
|--------|-------|--------|
| `target_allocation(strategy_weights, constraints)` | bobot strategi, batasan | alokasi target |
| `check_rebalance_trigger(current_alloc, target_alloc, rule)` | alokasi kini vs target, rule (threshold/calendar) | boolean trigger + daftar deviasi |
| `generate_rebalance_orders(current_alloc, target_alloc)` | alokasi kini & target | daftar order beli/jual |
| `attribute_performance(returns, factor_exposures)` | return portofolio, eksposur faktor | breakdown kontribusi performa |

**Terhubung dengan (Dependencies):**

- **Upstream:** Decision Engine, Risk Engine, Corporate Action Engine
- **Downstream:** Execution Engine (mengeksekusi order hasil rebalance)

---

#### 3.4.3 Execution Engine

**Tujuan:** Menghitung biaya transaksi dan mengeksekusi order secara realistis.

**Parameter yang Dihitung:**

- Brokerage fee (sesuai broker Indonesia)
- PPh final 0.1% atas penjualan saham
- Levy / biaya bursa (0.00043%)
- Slippage estimasi
- Bid-ask spread
- Market impact estimation
- Settlement date (T+2 untuk saham Indonesia)

**Output:**

- Net profit/loss per trade setelah biaya
- Break-even price
- Order feasibility check

**Input:**

- `rebalance_order_list` dari Portfolio Engine atau order langsung dari Decision Engine (mode non-portfolio/single-signal)
- Data bid-ask spread & volume real-time (untuk estimasi slippage)

**Fungsi Utama:**

| Fungsi | Input | Output |
|--------|-------|--------|
| `compute_fees(order_value, broker_config)` | nilai order, konfigurasi broker | brokerage fee, levy, PPh |
| `estimate_slippage(order_size, avg_volume, spread)` | ukuran order, volume, spread | estimasi slippage |
| `check_feasibility(order, available_cash, liquidity)` | order, kas tersedia, likuiditas | status feasible/reject |
| `simulate_fill(order, market_state)` | order, kondisi pasar (live/backtest) | harga fill, timestamp settlement (T+2) |

**Output tambahan:** Event `execution.order.filled` / `execution.order.rejected`

**Terhubung dengan (Dependencies):**

- **Upstream:** Portfolio Engine, Decision Engine
- **Downstream:** Backtesting Engine (mode simulasi), Paper Trading Module, audit log

---

### 3.5 Decision & Learning Layer

#### 3.5.1 Decision Engine

**Tujuan:** Menggabungkan output dari semua engine menjadi sinyal yang dapat dieksekusi.

**Cara Kerja:**

1. Collect scores dari setiap engine
2. Apply regime filter (market regime, macro regime, risk regime)
3. Apply risk filter (position sizing, max drawdown, liquidity)
4. Generate decision: `BUY`, `HOLD`, `SELL`, `AVOID`, `WATCHLIST`
5. Priority ranking berdasarkan conviction score

**Input:**

- Fundamental score
- Technical score
- Macro compatibility score
- Global market compatibility score
- Sentiment score
- Risk-adjusted expected return

**Output:**

- Recommendation object dengan:
  - `action`
  - `ticker`
  - `conviction_score` (0–100)
  - `position_size`
  - `entry_price_range`
  - `stop_loss`
  - `take_profit`
  - `expected_hold_period`
  - `risk_flags`

**Fungsi Utama:**

| Fungsi | Input | Output |
|--------|-------|--------|
| `collect_scores(ticker)` | ticker | dict skor dari semua engine (fundamental, technical, macro, global, sentiment, relationship) |
| `apply_regime_filter(scores, regimes)` | skor + regime aktif (market/macro/risk) | skor terfilter/ter-adjust |
| `apply_risk_filter(candidate, risk_engine_result)` | kandidat + hasil Risk Engine | kandidat final atau `AVOID` |
| `compute_conviction(scores, weights)` | skor terfilter + bobot faktor (dari AI Learning Engine) | `conviction_score` |
| `rank(candidates)` | daftar kandidat rekomendasi | daftar terurut berdasarkan conviction |

**Terhubung dengan (Dependencies):**

- **Upstream:** Semua engine di Analysis Layer & Intelligence Layer (skor), Risk Engine (filter), AI Learning Engine (bobot faktor)
- **Downstream:** Portfolio Engine, Execution Engine, Explainable AI Engine, Presentation Layer (Dashboard/Alerts)
- **Event Bus:** konsumsi `analysis.*.score`, `analysis.relationship.updated`, `risk.assessment.completed`; publikasi `decision.recommendation.created`

---

#### 3.5.2 AI Learning Engine

**Tujuan:** Menemukan pola, menghitung bobot faktor, dan meningkatkan kualitas keputusan dari waktu ke waktu.

**Prinsip Penting:**

> **AI membantu, bukan mengambil alih keputusan.** Keputusan final tetap dalam kendali sistem yang dapat diaudit dan divalidasi.

**Aplikasi AI:**

1. **Factor Weight Optimization**
   - Menggunakan regresi, random forest, atau gradient boosting untuk menilai kontribusi faktor historis

2. **Regime Classification**
   - Hidden Markov Model atau clustering untuk mengidentifikasi regime pasar

3. **Feature Importance**
   - SHAP, permutation importance, LIME

4. **Pattern Recognition**
   - Deteksi pola teknis (chart pattern) menggunakan machine learning atau rule-based hybrid

5. **Score Fusion**
   - Menggabungkan multi-factor scores secara adaptif

**Input:**

- Data historis hasil Backtesting/Paper Trading (`trade_history`, `equity_curve`)
- Skor mentah dari seluruh Analysis Layer beserta hasil realisasi (label return forward)

**Output:**

- `factor_weights` (bobot per faktor, per regime jika relevan) — dikonsumsi Decision Engine
- `regime_model` (parameter HMM/cluster) — dikonsumsi engine yang butuh regime
- `feature_importance_report`

**Fungsi Utama:**

| Fungsi | Input | Output |
|--------|-------|--------|
| `train_factor_weight_model(feature_matrix, forward_returns)` | fitur historis + return realisasi | model + `factor_weights` |
| `fit_regime_model(market_series)` | seri pasar historis | `regime_model` |
| `compute_feature_importance(model, feature_matrix)` | model terlatih + fitur | ranking importance (SHAP/permutation) |
| `fuse_scores(scores, weights)` | skor multi-faktor + bobot | skor gabungan |

**Terhubung dengan (Dependencies):**

- **Upstream:** Backtesting Engine, Paper Trading Module (data hasil realisasi), Analysis Layer (fitur)
- **Downstream:** Decision Engine (`factor_weights`), Explainable AI Engine (feature importance), engine regime-aware lainnya

---

#### 3.5.3 Explainable AI Engine

**Tujuan:** Memberikan alasan yang jelas untuk setiap rekomendasi.

**Pertanyaan yang Dijawab:**

- Mengapa rekomendasi `BUY`, `HOLD`, atau `SELL`?
- Faktor apa yang paling memengaruhi rekomendasi ini?
- Seberapa yakin sistem dengan rekomendasi tersebut?
- Risiko apa saja yang dapat membatalkan rekomendasi ini?
- Bagaimana performa strategi serupa di masa lalu?

**Output:**

- Explanation report per rekomendasi
- Top contributing factors dengan magnitude
- Confidence interval dan uncertainty estimate
- Counter-scenario analysis ("What if oil drops 10%?")

**Input:**

- `decision.recommendation.created` (rekomendasi lengkap dengan skor komponen) dari Decision Engine
- `feature_importance_report` dari AI Learning Engine

**Fungsi Utama:**

| Fungsi | Input | Output |
|--------|-------|--------|
| `generate_explanation(recommendation, contributing_scores)` | rekomendasi + skor per faktor | narasi alasan + top factors |
| `estimate_confidence(conviction_score, historical_accuracy)` | conviction + akurasi historis strategi sejenis | confidence interval |
| `counterfactual(recommendation, scenario)` | rekomendasi + skenario perubahan variabel | dampak simulasi terhadap conviction |

**Output tambahan:** Event `xai.explanation.generated`

**Terhubung dengan (Dependencies):**

- **Upstream:** Decision Engine, AI Learning Engine
- **Downstream:** Presentation Layer (Dashboard, Report Generator, Audit Logs)

---

### 3.6 Infrastructure Layer

#### 3.6.1 Monitoring Engine (24/7)

**Tugas:**

- Pantau perubahan data global secara otomatis
- Alert untuk anomali harga, volume, berita penting, atau data error
- Health check semua engine dan pipeline data
- Status dashboard sistem

**Input:**

- `data.quality.alert` dari Data Quality Validation Engine
- Heartbeat/health-check response dari seluruh engine (via Event Bus atau endpoint `/health`)

**Output:**

- `system_health_status` (per engine: UP/DOWN/DEGRADED)
- Notifikasi alert (email, Telegram, dashboard) untuk anomali kritikal

**Fungsi Utama:**

| Fungsi | Input | Output |
|--------|-------|--------|
| `poll_health(engine_list)` | daftar engine | status tiap engine |
| `detect_anomaly(metric_stream)` | stream metrik (harga/volume/latency) | flag anomali |
| `send_alert(anomaly, channel)` | detail anomali, kanal notifikasi | notifikasi terkirim |

**Terhubung dengan (Dependencies):**

- **Upstream:** Semua layer (menerima heartbeat/event)
- **Downstream:** Presentation Layer (Status Dashboard), tim operasional (alert channel)

---

#### 3.6.2 Backtesting Engine

**Tujuan:** Menguji strategi secara serius, bukan hanya melihat profit.

**Metrik yang Dihitung:**

| Metrik | Deskripsi |
|--------|-----------|
| Total Return | Return keseluruhan periode backtest |
| CAGR | Compound Annual Growth Rate |
| Max Drawdown | Penurunan tertinggi dari peak ke trough |
| Sharpe Ratio | Return dibanding risiko |
| Sortino Ratio | Risiko downside saja |
| Calmar Ratio | CAGR / Max Drawdown |
| Win Rate | Persentase trade yang profit |
| Profit Factor | Gross profit / gross loss |
| Average Win / Loss | Rata-rata profit dan loss per trade |
| Expectancy | Expected return per trade |
| Volatility | Standar deviasi return |
| Beta / Alpha | Terhadap benchmark (IHSG) |
| Number of Trades | Frekuensi trading |
| Exposure Time | Waktu terinvestasi |

**Fitur Penting:**

- Walk-forward analysis
- Out-of-sample testing
- Transaction cost modeling (fee, pajak, slippage)
- Regime-aware backtest (boom, bust, sideways)
- Overfitting detection (combination test, randomization test)

**Input:**

- Data historis bersih (`data.clean.*`) dari Data Storage, rentang tanggal sesuai periode uji
- Definisi strategi (aturan entry/exit, parameter) dari Strategy Editor (Presentation Layer)

**Output:**

- `backtest_report` (seluruh metrik pada tabel di atas)
- `trade_history`, `equity_curve` — dikonsumsi AI Learning Engine untuk pelatihan

**Fungsi Utama:**

| Fungsi | Input | Output |
|--------|-------|--------|
| `run_backtest(strategy, price_data, cost_model)` | definisi strategi, data harga, model biaya | `trade_history`, `equity_curve` |
| `compute_metrics(trade_history, equity_curve, benchmark)` | histori trade & equity, benchmark IHSG | seluruh metrik performa |
| `walk_forward(strategy, price_data, window)` | strategi, data, ukuran window | hasil per periode out-of-sample |
| `overfitting_test(strategy, price_data)` | strategi, data | skor risiko overfitting |

**Terhubung dengan (Dependencies):**

- **Upstream:** Data Storage, Execution Engine (cost model), Strategy Editor
- **Downstream:** AI Learning Engine, Paper Trading Module (baseline pembanding), Presentation Layer (Report Generator)

---

#### 3.6.3 Paper Trading Module

- Jalankan strategi dengan data real-time tanpa uang sungguhan
- Bandingkan hasil paper trading vs backtest
- Validasi slippage dan execution quality

**Input:**

- `decision.recommendation.created` (live) dari Decision Engine
- Data harga real-time/near-real-time dari Data Acquisition Engine

**Output:**

- `paper_trade_log` (order simulasi, fill price, PnL)
- Perbandingan `paper_vs_backtest_deviation` (slippage riil vs estimasi backtest)

**Fungsi Utama:**

| Fungsi | Input | Output |
|--------|-------|--------|
| `simulate_live_order(recommendation, live_price)` | rekomendasi, harga live | order simulasi + fill |
| `compare_with_backtest(paper_trade_log, backtest_report)` | log paper trading, laporan backtest | deviasi performa |

**Terhubung dengan (Dependencies):**

- **Upstream:** Decision Engine, Data Acquisition Engine, Execution Engine (model biaya)
- **Downstream:** AI Learning Engine (feedback loop), Monitoring Engine

---

## 4. Kontrak Data (Data Contracts)

Setiap event yang mengalir di Event Bus dan setiap tabel penyimpanan mengikuti skema baku berikut. Tujuannya agar setiap engine dapat dikembangkan secara independen tanpa harus membaca kode engine lain — cukup mengikuti kontrak skema.

### 4.1 `ohlcv_record` (harga & volume)

```json
{
  "ticker": "BBCA.JK",
  "asset_class": "equity",
  "exchange": "IDX",
  "timestamp": "2026-07-29T00:00:00+07:00",
  "timeframe": "1d",
  "open": 9500, "high": 9575, "low": 9475, "close": 9550,
  "volume": 12500000,
  "adjusted_close": 9550,
  "source": "IDX",
  "ingested_at": "2026-07-29T20:05:00+07:00"
}
```

### 4.2 `fundamental_record` (laporan keuangan per periode)

```json
{
  "ticker": "BBCA.JK",
  "period": "2026-Q2",
  "period_type": "quarterly",
  "statement": {
    "revenue": 0, "net_income": 0, "total_equity": 0, "total_debt": 0,
    "operating_cash_flow": 0, "eps": 0
  },
  "restated": false,
  "source": "BEI",
  "ingested_at": "2026-07-29T20:05:00+07:00"
}
```

### 4.3 `macro_record`

```json
{
  "indicator": "BI_RATE",
  "country": "ID",
  "period": "2026-07",
  "actual": 5.75,
  "consensus": 5.75,
  "previous": 5.75,
  "unit": "percent",
  "source": "BI"
}
```

### 4.4 `news_record`

```json
{
  "news_id": "uuid",
  "headline": "...",
  "body": "...",
  "published_at": "2026-07-29T10:00:00+07:00",
  "source": "NewsAPI",
  "entities": [{"type": "ticker", "value": "BBCA.JK"}],
  "topic": ["corporate"],
  "url": "https://..."
}
```

### 4.5 `corporate_action_record`

```json
{
  "ticker": "BBCA.JK",
  "action_type": "dividend",
  "announce_date": "2026-06-01",
  "ex_date": "2026-06-15",
  "record_date": "2026-06-16",
  "payment_date": "2026-07-01",
  "value": 150,
  "unit": "IDR_per_share"
}
```

### 4.6 `score_record` (output umum semua Analysis Engine)

```json
{
  "ticker": "BBCA.JK",
  "engine": "fundamental",
  "score": 78.5,
  "breakdown": {"PER": 0.7, "ROE": 0.9, "DER": 0.6},
  "as_of": "2026-07-29T20:10:00+07:00"
}
```

### 4.7 `recommendation_record` (output Decision Engine)

```json
{
  "recommendation_id": "uuid",
  "ticker": "BBCA.JK",
  "action": "BUY",
  "conviction_score": 82,
  "position_size": 0.05,
  "entry_price_range": [9500, 9600],
  "stop_loss": 9200,
  "take_profit": 10200,
  "expected_hold_period": "3-6 months",
  "risk_flags": [],
  "contributing_scores": {"fundamental": 78.5, "technical": 65, "macro": 70, "sentiment": 55},
  "created_at": "2026-07-29T20:15:00+07:00"
}
```

---

## 5. Alur Data End-to-End (Data Flow)

Alur berikut menggambarkan bagaimana satu siklus keputusan terbentuk, dari data mentah hingga rekomendasi yang dapat dieksekusi:

```
[1] Scheduler memicu Data Acquisition Engine
        │
        ▼
[2] Data Acquisition Engine → fetch & normalize → publish event data.raw.*
        │
        ▼
[3] Data Quality Validation Engine → validasi, cross-check, reconcile
        │  (gagal validasi → flag anomali → Monitoring Engine → alert)
        ▼
[4] Data Storage (clean_zone) → publish event data.clean.*
        │
        ├──────────────► Fundamental Analysis Engine ─┐
        ├──────────────► Technical Analysis Engine ───┤
        ├──────────────► Macro Economic Engine ────────┤
        ├──────────────► Global Market Engine ─────────┼──► analysis.*.score
        ├──────────────► News & Sentiment Engine ───────┤
        ├──────────────► Corporate Action Engine ───────┘
        │
        ▼
[5] Market Relationship Engine (mengonsumsi data.clean.* + analysis.macro.regime)
        │  → analysis.relationship.updated
        ▼
[6] Decision Engine
        │  - collect_scores() dari semua event analysis.*.score + analysis.relationship.updated
        │  - apply_regime_filter()
        │  - kirim kandidat ke Risk Engine
        ▼
[7] Risk Engine → risk.assessment.completed (position size, SL/TP, risk flags)
        │
        ▼
[8] Decision Engine → apply_risk_filter() → decision.recommendation.created
        │
        ├──► Explainable AI Engine → xai.explanation.generated
        ├──► Portfolio Engine → portfolio.rebalance.generated
        └──► Presentation Layer (Dashboard, Alerts)
        ▼
[9] Execution Engine → execution.order.filled / rejected
        │
        ▼
[10] Backtesting Engine (offline) / Paper Trading Module (live) → trade_history, equity_curve
        │
        ▼
[11] AI Learning Engine → melatih ulang factor_weights & regime_model dari hasil realisasi
        │
        └──► kembali memengaruhi Decision Engine (langkah 6) pada siklus berikutnya
```

**Catatan penting:**

- Langkah 2–4 berjalan terjadwal (batch harian/intraday) sesuai jenis data.
- Langkah 6–9 dapat berjalan on-demand (dipicu saat ada data baru relevan) maupun terjadwal (misal setiap penutupan sesi).
- Langkah 10–11 berjalan sebagai proses offline/berkala (mis. mingguan) untuk retraining, bukan bagian dari jalur keputusan real-time.

---

## 6. Event Bus & API Contract

### 6.1 Daftar Topic Event Bus

| Topic | Publisher | Subscriber |
|-------|-----------|------------|
| `data.raw.ohlcv`, `data.raw.fundamental`, `data.raw.news`, `data.raw.corporate_action` | Data Acquisition Engine | Data Quality Validation Engine |
| `data.clean.ohlcv`, `data.clean.fundamental`, `data.clean.macro`, `data.clean.calendar` | Data Quality Validation Engine | Semua Analysis Engine, Market Relationship Engine |
| `data.quality.alert` | Data Quality Validation Engine | Monitoring Engine |
| `analysis.fundamental.score` | Fundamental Analysis Engine | Decision Engine, XAI Engine |
| `analysis.technical.score` | Technical Analysis Engine | Decision Engine, XAI Engine |
| `analysis.macro.regime` | Macro Economic Engine | Decision Engine, Market Relationship Engine, Risk Engine |
| `analysis.global.score` | Global Market Engine | Decision Engine, Market Relationship Engine |
| `analysis.sentiment.score` | News & Sentiment Engine | Decision Engine, XAI Engine |
| `analysis.corporate_action.updated` | Corporate Action Engine | Fundamental/Technical Analysis Engine, Portfolio Engine |
| `analysis.relationship.updated` | Market Relationship Engine | Decision Engine, XAI Engine |
| `risk.assessment.completed` | Risk Engine | Decision Engine, Portfolio Engine |
| `decision.recommendation.created` | Decision Engine | Portfolio Engine, XAI Engine, Presentation Layer, Paper Trading Module |
| `portfolio.rebalance.generated` | Portfolio Engine | Execution Engine |
| `execution.order.filled`, `execution.order.rejected` | Execution Engine | Backtesting/Paper Trading, Audit Log |
| `xai.explanation.generated` | Explainable AI Engine | Presentation Layer |

### 6.2 Kontrak REST API (ringkas, per layer)

| Endpoint | Method | Fungsi |
|----------|--------|--------|
| `/api/data/{category}` | GET | Ambil data bersih (ohlcv/fundamental/macro/news) dengan filter ticker & rentang tanggal |
| `/api/scores/{ticker}` | GET | Ambil seluruh skor terbaru (fundamental/technical/macro/global/sentiment) untuk satu ticker |
| `/api/recommendations` | GET | Ambil daftar rekomendasi aktif, dapat difilter by action/conviction |
| `/api/recommendations/{id}/explanation` | GET | Ambil laporan penjelasan (XAI) untuk satu rekomendasi |
| `/api/portfolio` | GET | Ambil posisi & alokasi portofolio saat ini |
| `/api/backtest` | POST | Jalankan backtest untuk strategi & rentang tanggal tertentu |
| `/api/backtest/{id}/report` | GET | Ambil laporan hasil backtest |
| `/api/health` | GET | Status kesehatan seluruh engine (dikonsumsi Monitoring Engine/Dashboard) |

---

## 7. Skema Database (ERD Ringkas)

Tabel-tabel inti (nama indikatif, dapat disesuaikan dengan pilihan teknologi pada §10):

| Tabel | Kolom Utama | Ditulis oleh | Dibaca oleh |
|-------|--------------|--------------|-------------|
| `ohlcv` | ticker, timestamp, timeframe, open, high, low, close, volume, adjusted_close, source | Data Acquisition/Validation Engine | Technical/Fundamental Engine, Backtesting |
| `fundamental_statements` | ticker, period, period_type, revenue, net_income, ..., restated, version | Data Validation Engine | Fundamental Analysis Engine |
| `macro_indicators` | indicator, country, period, actual, consensus, previous, revised_at | Data Validation Engine | Macro Economic Engine |
| `news` | news_id, headline, body, published_at, entities, topic | Data Acquisition Engine | News & Sentiment Engine |
| `corporate_actions` | ticker, action_type, ex_date, record_date, payment_date, value | Corporate Action Engine | Fundamental/Technical Engine, Portfolio Engine |
| `scores` | ticker, engine, score, breakdown (JSON), as_of | Semua Analysis Engine | Decision Engine, XAI Engine |
| `relationship_matrix` | asset_a, asset_b, window, correlation, lag, updated_at | Market Relationship Engine | Decision Engine, XAI Engine |
| `recommendations` | recommendation_id, ticker, action, conviction_score, position_size, entry/sl/tp, created_at | Decision Engine | Portfolio Engine, Execution Engine, Presentation Layer |
| `positions` | ticker, quantity, avg_price, opened_at, strategy_id | Execution Engine | Portfolio Engine, Risk Engine |
| `trade_history` | trade_id, ticker, entry/exit price & time, pnl, fees, strategy_id | Execution Engine, Backtesting Engine | AI Learning Engine, Portfolio Engine |
| `equity_curve` | timestamp, equity, drawdown, strategy_id | Backtesting Engine, Paper Trading Module | AI Learning Engine, Presentation Layer |
| `factor_weights` | factor_name, weight, regime, trained_at | AI Learning Engine | Decision Engine |
| `audit_log` | event_id, event_type, payload (JSON), timestamp, actor | Semua engine (write-once) | Explainable AI Engine, Compliance/Audit |
| `source_health` | source, last_success, last_error, status | Data Acquisition Engine | Monitoring Engine |

**Prinsip desain skema:**

- Semua tabel skor/rekomendasi/trade menyimpan `as_of`/`created_at` agar historis dapat direkonstruksi (mendukung prinsip Auditabilitas di §11).
- Data yang direvisi (mis. laporan keuangan, data makro) menggunakan `version`/`revised_at`, bukan overwrite langsung — mendukung Reconciliation Engine (§3.1.2).
- `audit_log` bersifat append-only (write-once), tidak boleh di-update atau dihapus.

---

## 8. Hal-Hal yang Sering Terlupakan

| Masalah | Mitigasi |
|---------|----------|
| Regime pasar berubah | Regime detection + adaptive factor weights |
| Korelasi antaraset dinamis | Rolling correlation, stress scenario testing |
| Biaya dan slippage menggerus profit | Realistic cost model dalam backtest dan live |
| Data makro direvisi | Simpan revisi data, re-run backtest dengan data revised |
| Likuiditas terbatas | Volume filter, slippage model, max position size |
| Overfitting pada data historis | Out-of-sample test, walk-forward, regularisasi |
| Survivorship bias | Sertakan saham delisted dalam backtest |
| Look-ahead bias | Pastikan data hanya tersedia saat waktunya |
| Data sumber tidak konsisten | Cross-source validation dan reconciliation |
| Black swan events | Stress testing dan drawdown circuit breaker |

---

## 9. Roadmap Implementasi Bertahap

### Fase 1 — Fondasi Data & Backtest (Paling Penting)

- [ ] Bangun Data Acquisition Engine untuk harga saham Indonesia dan global
- [ ] Implementasikan Data Quality Validation Engine
- [ ] Simpan data dalam time-series database / data lake sederhana
- [ ] Bangun Backtesting Engine dengan transaction cost model yang realistis
- [ ] Buat 2–3 strategi sederhana sebagai benchmark (buy & hold, moving average crossover)
- [ ] Implementasikan metrik kinerja lengkap

**Deliverable:** Sistem dapat mengambil data bersih, menjalankan backtest, dan menghasilkan laporan metrik.

---

### Fase 2 — Analysis Layer Dasar

- [ ] Fundamental Analysis Engine dengan rasio utama
- [ ] Technical Analysis Engine (tren, momentum, volatilitas, volume profile)
- [ ] Macro Economic Engine untuk data BI Rate, inflasi, PDB, yield
- [ ] Global Market Engine untuk bursa utama dunia

**Deliverable:** Setiap saham dapat diberi skor fundamental, teknikal, makro, dan global.

---

### Fase 3 — Relationship, Sentiment & Corporate Action

- [ ] Market Relationship Engine (pengaruh pasar AS, Tiongkok, minyak ke IHSG/sektor)
- [ ] Corporate Action Engine dan adjusted price calculation
- [ ] News & Sentiment Engine sederhana (klasifikasi dan skor sentimen)

**Deliverable:** Sistem memahami konteks pasar global, aksi korporasi, dan narasi berita.

---

### Fase 4 — Decision, Risk, Portfolio & Execution

- [ ] Risk Engine (position sizing, stop loss, drawdown, diversifikasi)
- [ ] Portfolio Engine (alokasi modal dan rebalancing)
- [ ] Execution Engine (biaya, pajak, slippage, spread)
- [ ] Decision Engine yang menggabungkan semua skor

**Deliverable:** Sistem menghasilkan rekomendasi lengkap dengan ukuran posisi, SL, TP, dan biaya.

---

### Fase 5 — AI, Explainability & Continuous Improvement

- [ ] AI Learning Engine untuk bobot faktor dan regime detection
- [ ] Explainable AI Engine untuk laporan alasan rekomendasi
- [ ] Monitoring Engine 24/7
- [ ] Paper Trading dan continuous feedback loop

**Deliverable:** Sistem adaptif, dapat menjelaskan keputusan, dan belajar dari hasil.

---

## 10. Teknologi yang Direkomendasikan (Bersifat Indikatif)

Pemilihan didasarkan pada kebutuhan tiap engine di `§3` dan kontrak di `§6`: Backend perlu ekosistem data science/ML yang matang (Python), Middleware perlu penanganan event async & orchestration yang reliable, Frontend perlu dashboard interaktif dengan chart finansial real-time.

### 10.1 Backend (BE) — Engine & Business Logic

| Kebutuhan | Teknologi Pilihan | Alasan |
|-----------|-------------------|--------|
| Bahasa utama seluruh Engine (§3.1–3.6) | **Python 3.11+** | Ekosistem data/ML terlengkap (Pandas, Polars, scikit-learn, dsb.), semua fungsi di §3 (mis. `compute_ratios`, `train_factor_weight_model`) native di Python |
| Framework API tiap engine | **FastAPI** | Async native, cocok untuk endpoint `/api/*` di §6.2, otomatis generate OpenAPI schema untuk kontrak §4 |
| Backtesting | **Backtrader, vectorbt, atau custom engine** | vectorbt lebih cepat untuk vectorized backtest skala besar |
| Machine Learning | **scikit-learn, XGBoost, LightGBM, SHAP** | Untuk AI Learning Engine (§3.5.2) dan Explainable AI Engine (§3.5.3) |
| NLP / Sentiment | **spaCy / HuggingFace Transformers (IndoBERT)** | Untuk News & Sentiment Engine (§3.3.5), mendukung entity-level sentiment Bahasa Indonesia |
| Time-series DB | **TimescaleDB (Postgres extension) atau InfluxDB** | Menyimpan `ohlcv`, `equity_curve` (§7) dengan query time-range efisien |
| Relational DB | **PostgreSQL** | Menyimpan `recommendations`, `positions`, `audit_log`, `factor_weights` (§7) — butuh transaksi ACID |

### 10.2 Middleware — Orkestrasi, Event Bus, & Integrasi

| Kebutuhan | Teknologi Pilihan | Alasan |
|-----------|-------------------|--------|
| Event Bus (topic §6.1) | **Redis Pub/Sub (awal) → Apache Kafka (skala besar)** | Redis cukup untuk MVP; Kafka jika volume event tinggi & butuh replay/durability |
| Task Queue (job async per engine) | **Celery + Redis/RabbitMQ** | Menjalankan `fetch()`, `run_backtest()`, `train_factor_weight_model()` sebagai job async, non-blocking API |
| Scheduler / Pipeline (memicu Data Acquisition, retraining) | **Apache Airflow atau Prefect** | Mengatur DAG dependency antar-tahap alur §5 (fetch → validate → analyze → decide) |
| API Gateway | **FastAPI Gateway / Kong / Nginx** | Satu pintu masuk untuk seluruh endpoint §6.2, menangani rate-limit & auth sebelum masuk ke tiap engine |
| Autentikasi & Otorisasi | **OAuth2 / JWT (FastAPI Security)** | Mengamankan akses ke Strategy Editor, Report Generator, Audit Logs (Presentation Layer) |
| Caching | **Redis** | Cache `scores`, `recommendations` yang sering diakses Dashboard agar tidak membebani DB |

### 10.3 Frontend (FE) — Dashboard, Alerts, Strategy Editor

| Kebutuhan | Teknologi Pilihan | Alasan |
|-----------|-------------------|--------|
| Framework utama | **Next.js (React) + TypeScript** | SSR/SSG untuk performa, ekosistem komponen luas, cocok untuk dashboard produksi (lebih scalable dibanding Streamlit/Dash untuk jangka panjang) |
| Styling & Komponen | **TailwindCSS + shadcn/ui** | Konsisten, cepat membangun UI kompleks (tabel rekomendasi, filter, form Strategy Editor) |
| Chart Finansial | **TradingView Lightweight Charts / Recharts** | Lightweight Charts untuk candlestick/indikator teknikal (§3.3.2); Recharts untuk chart metrik backtest (§3.6.2) |
| Realtime update | **WebSocket (Socket.IO) atau Server-Sent Events** | Menerima event `decision.recommendation.created`, `data.quality.alert` (§6.1) secara live tanpa polling |
| State/Data Fetching | **TanStack Query (React Query)** | Sinkronisasi state FE dengan endpoint `/api/*` (§6.2), caching, auto-refetch |
| Alerting (channel eksternal) | **Telegram Bot API / Email (SMTP)** | Notifikasi dari Monitoring Engine (§3.6.1) dan `risk_flags` kritikal |

**Catatan alternatif MVP cepat:** Untuk fase awal riset/backtest internal sebelum FE produksi dibangun, **Streamlit** atau **Dash** dapat dipakai sebagai dashboard sementara (baca-saja) di atas endpoint yang sama, tanpa menghambat pengembangan Next.js secara paralel.

### 10.3.1 Prinsip UX: Transparansi Proses (Process Observability)

**Keputusan desain:** FE bukan hanya menampilkan hasil akhir (`recommendation_record`), tetapi juga **memvisualisasikan seluruh alur `§5`** — dari data masuk sampai keputusan keluar — agar user (dan auditor) dapat menelusuri *mengapa* dan *bagaimana* setiap angka terbentuk. Ini adalah implementasi langsung dari prinsip **Explainable** dan **Data First** (`§1`).

**Halaman/Komponen FE yang wajib ada, dipetakan ke tahap alur (`§5`):**

| Halaman/Komponen | Tahap `§5` yang divisualisasikan | Data Sumber (API/Event) |
|-------------------|-----------------------------------|--------------------------|
| **Market Overview / Chart Utama** | [4] Data bersih per ticker | `GET /api/data/{category}`, chart candlestick + indikator (Lightweight Charts) |
| **Pipeline Status (Live Flow Diagram)** | [1]–[11] status tiap tahap secara real-time (mis. node "Data Validation" hijau/kuning/merah) | `GET /api/health`, event `data.quality.alert`, `system_health_status` |
| **Score Breakdown Panel** | [4] hasil tiap Analysis Engine per ticker | `GET /api/scores/{ticker}` → render sebagai radar chart/bar per engine (fundamental/technical/macro/global/sentiment) |
| **Relationship Explorer** | [5] Market Relationship Engine | `relationship_matrix` → heatmap korelasi antaraset |
| **Decision Trace / "Why this recommendation?"** | [6]–[8] Decision Engine + Risk Engine + XAI Engine | `GET /api/recommendations/{id}/explanation` → tampilkan `contributing_scores`, `risk_flags`, narasi XAI, counter-scenario |
| **Order & Execution Log** | [9] Execution Engine | event `execution.order.filled/rejected` → tabel fee, slippage, net PnL |
| **Backtest Runner & Report** | [10] Backtesting Engine | `POST /api/backtest`, `GET /api/backtest/{id}/report` → equity curve, semua metrik `§3.6.2` |
| **Model Insight (AI Learning)** | [11] AI Learning Engine | `factor_weights`, `feature_importance_report` → bar chart bobot faktor per regime, riwayat retraining |
| **Audit Log Viewer** | Semua tahap (append-only) | tabel `audit_log` (`§7`) → filter by event_type/timestamp/actor, mendukung rekonstruksi keputusan historis |

**Prinsip implementasi:**

- **Live status, bukan hanya hasil akhir** — Pipeline Status Panel harus merefleksikan `system_health_status` (`§3.6.1`) secara real-time via WebSocket, sehingga user melihat *sedang berjalan tahap apa*, bukan cuma output jadi.
- **Setiap angka bisa "diklik untuk dijelaskan"** — Setiap skor/rekomendasi di UI harus punya link/drill-down ke Decision Trace (memanggil `xai.explanation.generated`), bukan angka mati.
- **Konsisten dengan gaya TradingView** — panel-panel di atas disusun sebagai layout multi-pane (chart utama besar + sidebar panel kanan untuk score/decision trace), meniru pola workspace TradingView agar familiar bagi trader.
- **Tidak menampilkan proses training/berat secara sinkron** — proses AI Learning Engine (retraining) berjalan async (Celery, `§10.2`); FE hanya menampilkan progress/status job, bukan blocking UI.

### 10.4 Infrastruktur & DevOps

| Kebutuhan | Teknologi Pilihan | Alasan |
|-----------|-------------------|--------|
| Containerization | **Docker, Docker Compose** | Setiap engine (§3) dapat dijalankan sebagai service terpisah, sejalan dengan prinsip Modular & Decoupled (§1) |
| Deployment | **VPS/Cloud (mis. AWS/GCP) atau on-prem** | Fleksibel sesuai skala; Docker Compose untuk awal, Kubernetes bila engine bertambah banyak |
| Monitoring & Observability | **Grafana + Prometheus** | Visualisasi `system_health_status` (§3.6.1) dan metrik latency antar-engine |
| Log Aggregation | **Loki atau ELK Stack** | Terpusatkan log seluruh engine untuk mendukung `audit_log` (§7) dan debugging |

---

## 11. Prinsip Keamanan & Auditabilitas

- Semua keputusan tercatat dalam audit log.
- Setiap rekomendasi dapat direkonstruksi dari data mentah pada saat itu.
- Tidak ada "magic number" tanpa justifikasi di backtest.
- Backtest harus out-of-sample dan mengikutsertakan biaya transaksi.
- AI hanya memberi bobot atau saran, bukan otoritas final.
- Sistem memiliki mode paper trading sebelum live trading.

---

## 12. Kesimpulan

Sistem ini dibangun untuk **tumbuh stabil dan dapat dipercaya**. Titik awalnya bukan AI yang rumit, melainkan:

1. **Data bersih**
2. **Backtest yang solid**
3. **Risk management yang ketat**

Setelah fondasi ini kokoh, modul analisis, keputusan, dan AI ditambahkan secara bertahap. Dengan arsitektur modular, setiap lapisan dapat diuji, diganti, dan ditingkatkan tanpa merusak sistem secara keseluruhan.
