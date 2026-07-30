# SISTEM TRADING PROFESIONAL

## Buku Panduan Teknis Lengkap

### Versi 0.1.0 — Phase 1–5

**Sistem Operasi Pengambilan Keputusan Investasi**

Berbasis Multi-Factor Analysis, Risk Management, dan Explainable AI

---

Dokumen ini disusun sebagai referensi teknis menyeluruh untuk arsitektur, implementasi, dan pengoperasian aplikasi Sistem Trading Profesional. Dokumen ini dioptimalkan untuk cetak pada kertas ukuran A4.

---

## Daftar Isi

| Bab | Judul |
|-----|-------|
| 1 | Pengantar dan Filosofi Sistem |
| 2 | Arsitektur Sistem |
| 3 | Struktur Proyek dan Dependensi |
| 4 | Konfigurasi Global |
| 5 | Data Layer: Akuisisi, Validasi, dan Penyimpanan |
| 6 | Analysis Layer: Technical, Fundamental, Macro, Global |
| 7 | Intelligence Layer: Market Relationship & Corporate Actions |
| 8 | Sentiment Engine |
| 9 | Risk Engine |
| 10 | Portfolio Engine |
| 11 | Execution Engine |
| 12 | Decision Engine |
| 13 | Explainable AI (XAI) Engine |
| 14 | AI Learning Engine |
| 15 | Paper Trading Engine |
| 16 | Monitoring Engine |
| 17 | Backtesting Engine |
| 18 | Analysis Pipeline: Orkestrasi Multi-Engine |
| 19 | API Layer (FastAPI) |
| 20 | Frontend: Dashboard dan Engine Monitor |
| 21 | CLI (Command-Line Interface) |
| 22 | Testing (E2E dengan Playwright) |
| 23 | Deployment dan Operasional |
| 24 | Roadmap Pengembangan |
| A | Skema Database SQLite |
| B | Data Contracts (Pydantic) |
| C | Engine Registry Lengkap |
| D | Glosarium |

---

# Bab 1: Pengantar dan Filosofi Sistem

## 1.1 Latar Belakang

Sistem Trading Profesional adalah aplikasi perangkat lunak yang dirancang untuk mengotomatisasi proses pengambilan keputusan investasi saham, khususnya di Bursa Efek Indonesia (IDX/BEI). Sistem ini tidak sekadar menghasilkan sinyal beli/jual, melainkan berfungsi sebagai **sistem operasi pengambilan keputusan investasi** yang terstruktur, dapat diaudit, dan mampu berkembang secara bertahap.

## 1.2 Prinsip Inti

Sistem ini dibangun di atas enam prinsip arsitektur yang memandu setiap keputusan desain:

1. **Data First** — Keputusan hanya sekuat data yang masuk. Setiap data yang masuk harus melalui validasi kualitas sebelum digunakan.
2. **Backtestable First** — Setiap hipotesis strategi harus dapat diuji secara historis dengan biaya transaksi realistis.
3. **Modular & Decoupled** — Setiap engine dapat dikembangkan, diuji, dan diganti secara independen tanpa memengaruhi modul lain.
4. **Explainable** — Setiap rekomendasi harus dapat dijelaskan faktor apa saja yang memengaruhinya, bukan kotak hitam.
5. **Risk-Aware** — Tanpa pengelolaan risiko, sistem tidak boleh menghasilkan sinyal. Risk Engine wajib berjalan sebelum Decision Engine.
6. **Continuous Learning** — AI tidak menggantikan keputusan manusia, melainkan membantu menemukan pola dan menyesuaikan bobot faktor dari waktu ke waktu.

## 1.3 Fase Pengembangan

| Fase | Fokus | Status |
|------|-------|--------|
| Phase 1 | Data Acquisition, Quality Validation, Storage, Backtest | Selesai |
| Phase 2 | Analysis Engines (Technical, Fundamental, Macro, Global) | Selesai |
| Phase 3 | Intelligence (Relationship, Corporate Actions, Sentiment) | Selesai |
| Phase 4 | Decision, Risk, Portfolio, Execution | Selesai |
| Phase 5 | XAI, AI Learning, Paper Trading, Monitoring, Frontend | Selesai |

## 1.4 Teknologi Utama

| Komponen | Teknologi |
|----------|-----------|
| Backend | Python 3.10+, FastAPI, Uvicorn |
| Database | SQLite (siap migrasi ke TimescaleDB) |
| Data Source | Yahoo Finance (yfinance) |
| Data Processing | Pandas, NumPy, PyArrow |
| Data Validation | Pydantic v2 |
| Frontend | Next.js 16, React 19, TypeScript, TailwindCSS v4 |
| Charting | Lightweight Charts (TradingView), Recharts |
| Testing | Pytest, Playwright |

---

# Bab 2: Arsitektur Sistem

## 2.1 Layered Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         PRESENTATION & COMMAND LAYER                          │
│  Dashboard (Next.js)  │  Engine Monitor (WebSocket)  │  CLI  │  API          │
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

## 2.2 Alur Data dan Keputusan

1. **Akuisisi Data** — `YahooFinanceAdapter` mengambil data OHLCV dari Yahoo Finance dengan rate limiting.
2. **Validasi Kualitas** — `DataQualityValidator` memeriksa completeness, plausibility, dan memberikan skor kualitas (0–100).
3. **Penyimpanan** — `DataStorage` menyimpan data bersih ke SQLite.
4. **Analisis Multi-Faktor** — `AnalysisPipeline` menjalankan tujuh engine analisis dan menghasilkan skor 0–100.
5. **Manajemen Risiko** — `RiskEngine` menghitung ATR, position sizing, stop loss, take profit, dan risk flags.
6. **Keputusan** — `DecisionEngine` menggabungkan semua skor dengan bobot tertentu, menerapkan regime filter, dan menghasilkan rekomendasi BUY/HOLD/WATCHLIST/AVOID.
7. **Penjelasan** — `ExplainableAIEngine` menghasilkan narasi penjelasan rekomendasi.

## 2.3 Pola Desain

| Pola | Penerapan |
|------|-----------|
| Adapter Pattern | `YahooFinanceAdapter` untuk sumber data eksternal |
| Strategy Pattern | `BuyAndHold` dan `MovingAverageCrossover` sebagai strategi backtest |
| Registry Pattern | `ENGINE_REGISTRY` di API untuk memantau semua engine |
| Pipeline Pattern | `AnalysisPipeline` mengorkestrasi eksekusi semua engine analisis |
| Repository Pattern | `DataStorage` sebagai abstraksi penyimpanan |
| Context Manager | `_connect()` di `DataStorage` untuk manajemen koneksi SQLite |

---

# Bab 3: Struktur Proyek dan Dependensi

## 3.1 Struktur Direktori

```
global/
├── README.md
├── pyproject.toml
├── requirements.txt
├── run_all.sh
├── data/
│   ├── raw/                       # Raw zone: file Parquet mentah
│   ├── clean/                     # Clean zone: data tervalidasi
│   └── trading_system.db          # Database SQLite
├── docs/
│   ├── arsitektur-sistem-trading.md
│   └── buku-sistem-trading.md     # Dokumen ini
├── src/
│   └── trading_system/
│       ├── __init__.py
│       ├── config.py              # Konfigurasi global
│       ├── cli.py                 # Command-line interface
│       ├── data/                  # Data Layer
│       │   ├── acquisition.py
│       │   ├── contracts.py
│       │   ├── storage.py
│       │   └── validation.py
│       ├── analysis/              # Analysis Layer
│       │   ├── pipeline.py
│       │   ├── technical.py
│       │   ├── fundamental.py
│       │   ├── macro.py
│       │   └── global_market.py
│       ├── intelligence/
│       │   └── relationship.py
│       ├── sentiment/
│       │   └── engine.py
│       ├── corporate/
│       │   └── actions.py
│       ├── risk/
│       │   └── engine.py
│       ├── portfolio/
│       │   └── engine.py
│       ├── execution/
│       │   └── engine.py
│       ├── decision/
│       │   └── engine.py
│       ├── xai/
│       │   └── engine.py
│       ├── ai_learning/
│       │   └── engine.py
│       ├── paper_trading/
│       │   └── engine.py
│       ├── monitoring/
│       │   └── engine.py
│       ├── backtest/
│       │   ├── engine.py
│       │   ├── strategies.py
│       │   └── metrics.py
│       └── api/
│           └── app.py
├── frontend/                      # Next.js frontend
│   ├── package.json
│   ├── next.config.ts
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   ├── globals.css
│   │   ├── dashboard/page.tsx
│   │   ├── engines/page.tsx
│   │   └── components/
│   │       ├── TerminalLayout.tsx
│   │       └── PriceChart.tsx
│   └── public/
└── tests/
    └── e2e/
        ├── test_dashboard.py
        └── record_demo.py
```

## 3.2 Dependensi Backend

| Package | Versi Minimum | Fungsi |
|---------|---------------|--------|
| pandas | >= 2.0.0 | Manipulasi data tabular |
| numpy | >= 1.24.0 | Komputasi numerik |
| yfinance | >= 0.2.28 | Sumber data pasar |
| pyarrow | >= 12.0.0 | Penyimpanan Parquet |
| sqlalchemy | >= 2.0.0 | Abstraksi database |
| pydantic | >= 2.0.0 | Validasi data contracts |
| fastapi | >= 0.100.0 | REST API framework |
| uvicorn[standard] | >= 0.23.0 | ASGI server |
| httpx | >= 0.24.0 | HTTP client |
| plotly | >= 5.15.0 | Plotting |
| python-dateutil | >= 2.8.2 | Utilitas tanggal |
| pytest | >= 7.4.0 | Testing framework |
| playwright | >= 1.40.0 | E2E browser testing |

## 3.3 Dependensi Frontend

| Package | Versi | Fungsi |
|---------|-------|--------|
| next | 16.2.12 | React framework |
| react | 19.2.4 | UI library |
| react-dom | 19.2.4 | React DOM renderer |
| lightweight-charts | ^5.2.0 | Candlestick chart |
| recharts | ^3.10.1 | Bar chart untuk factor scores |
| tailwindcss | ^4 | Utility-first CSS |
| typescript | ^5 | Type safety |
| eslint | ^9 | Linting |

---

# Bab 4: Konfigurasi Global

**File:** `src/trading_system/config.py`

## 4.1 Path dan Storage

```python
ROOT = Path(__file__).resolve().parents[2]     # Root proyek
DATA_DIR = ROOT / "data"
RAW_ZONE = DATA_DIR / "raw"                     # Raw zone (Parquet)
CLEAN_ZONE = DATA_DIR / "clean"                 # Clean zone
DB_PATH = DATA_DIR / "trading_system.db"        # SQLite database
```

Sistem menggunakan konsep **raw zone** dan **clean zone** untuk memisahkan data mentah dari data tervalidasi. Raw zone menyimpan file Parquet dengan timestamp, sedangkan clean zone menggunakan SQLite.

## 4.2 Parameter Biaya Transaksi (Bursa Efek Indonesia)

```python
DEFAULT_BROKER_FEE_BUY = 0.0015       # 0.15% biaya broker beli
DEFAULT_BROKER_FEE_SELL = 0.0025      # 0.15% broker + 0.1% PPh final
DEFAULT_LEVY = 0.0000043              # 0.00043% levy bursa efek
DEFAULT_SLIPPAGE = 0.0005             # 0.05% slippage default
```

Biaya jual lebih tinggi karena mencakup Pajak Penghasilan (PPh) final 0.1% atas penjualan saham.

## 4.3 Rate Limiting

```python
YFINANCE_RATE_LIMIT_CALLS = 1         # Maksimum 1 panggilan
YFINANCE_RATE_LIMIT_WINDOW = 1.0      # Per 1 detik
```

Menggunakan sliding window algorithm dengan `threading.Lock` untuk thread safety.

## 4.4 Benchmark

```python
DEFAULT_BENCHMARK = "^JKSE"           # Indeks Harga Saham Gabungan (IHSG)
```

## 4.5 Proxy Instrumen Makroekonomi

```python
DEFAULT_MACRO_TICKERS = {
    "US10Y": "^TNX",          # US Treasury 10Y yield
    "GOLD": "GC=F",            # Gold futures
    "OIL": "CL=F",             # Crude oil futures
    "USD_IDR": "IDR=X",        # USD/IDR exchange rate
    "DXY": "DX-Y.NYB",         # US Dollar Index
}
```

## 4.6 Proxy Indeks Pasar Global

```python
DEFAULT_GLOBAL_TICKERS = {
    "SP500": "^GSPC",          # S&P 500
    "NASDAQ": "^IXIC",         # Nasdaq Composite
    "DOW": "^DJI",             # Dow Jones Industrial Average
    "HANGSENG": "^HSI",        # Hang Seng Index
    "NIKKEI": "^N225",         # Nikkei 225
    "FTSE": "^FTSE",           # FTSE 100
    "DAX": "^GDAXI",           # DAX 40
}
```

Fungsi `ensure_dirs()` memastikan direktori `raw/` dan `clean/` selalu ada saat modul diimpor.

---

# Bab 5: Data Layer

## 5.1 Ikhtisar

Data Layer adalah fondasi sistem, terdiri dari tiga komponen:

1. **Data Acquisition Engine** — Mengambil data dari sumber eksternal
2. **Data Quality Validator** — Memvalidasi dan menilai kualitas data
3. **Data Storage** — Menyimpan data dengan skema terstruktur

## 5.2 Data Acquisition Engine

**File:** `src/trading_system/data/acquisition.py`

### 5.2.1 RateLimiter

Class `RateLimiter` mengimplementasikan sliding window rate limiting:

1. Menyimpan timestamp setiap panggilan API dalam list.
2. Sebelum panggilan baru, membersihkan timestamp di luar window.
3. Jika jumlah panggilan dalam window sudah mencapai limit, menunggu hingga timestamp tertua keluar dari window.
4. Mencatat timestamp panggilan baru.

Menggunakan `threading.Lock` untuk thread safety.

### 5.2.2 YahooFinanceAdapter

Method `fetch(ticker, period, interval)`:

1. Memanggil rate limiter.
2. Membuat `yf.Ticker(ticker)` dan memanggil `t.history(period, interval)`.
3. Jika data kosong, mengembalikan status `"empty"`.
4. Rename kolom Yahoo Finance ke skema internal: `Date`→`timestamp`, `Open`→`open`, `High`→`high`, `Low`→`low`, `Close`→`close`, `Volume`→`volume`.
5. Menambahkan metadata: `ticker`, `asset_class`, `exchange`, `timeframe`, `source`, `ingested_at`.
6. Menyimpan raw data sebagai Parquet di `raw_zone` dengan format `{ticker}_{interval}_{timestamp}.parquet`.
7. Mengupdate `source_health` dan menulis audit log.
8. Mengembalikan `{status, records, message}`.

Pada error: update `source_health` ke `"down"`, tulis audit log `data.raw.ohlcv.error`, kembalikan `status: "error"`.

### 5.2.3 Fungsi normalize_ohlcv

Melakukan normalisasi DataFrame mentah ke skema kontrak standar:

- Konversi `timestamp` ke string tanpa timezone.
- Tambah `adjusted_close` (sementara = `close`).
- Tambah `data_quality_score` (diisi validator).
- Urutkan kolom sesuai skema.

## 5.3 Data Quality Validator

**File:** `src/trading_system/data/validation.py`

### 5.3.1 Empat Jenis Pemeriksaan

**1. Completeness Check** — Menghitung persentase NaN. Skor dikurangi `missing_pct * 2`. Severity: medium.

**2. Plausibility Check:**
- Harga <= 0 → severity high, skor -2.0 per anomaly
- Low > High → severity high, skor -2.0
- Close di luar range [low, high] → severity high, skor -2.0

**3. Volume Spike** — Volume > 10x median → severity low, skor -1.0.

**4. Gap Detection** — Gap > 5 hari → severity low, skor -0.5.

### 5.3.2 Skor Kualitas dan Tindakan

| Skor | Tindakan | Arti |
|------|----------|------|
| >= 90 | `accept` | Data diterima sepenuhnya |
| 70–89 | `flag` | Diterima dengan flag untuk review |
| < 70 | `pause` | Data ditolak, tidak disimpan |

Setiap validasi mencatat audit log `data.quality.validation`.

## 5.4 Data Storage

**File:** `src/trading_system/data/storage.py`

### 5.4.1 Class DataStorage

Repository utama dengan SQLite. Context manager `_connect()` memastikan:
- `PRAGMA foreign_keys = ON`
- Auto-commit pada sukses, auto-rollback pada exception
- Koneksi selalu ditutup

### 5.4.2 Operasi Utama

| Method | Fungsi |
|--------|--------|
| `save_ohlcv(df)` | Simpan OHLCV dengan INSERT OR REPLACE |
| `load_ohlcv(ticker, start, end, timeframe)` | Muat OHLCV sebagai DataFrame |
| `list_tickers()` | Daftar ticker unik |
| `save_score(ticker, engine, score, breakdown)` | Simpan skor engine |
| `load_scores(ticker, engine)` | Muat skor, diurutkan `as_of` desc |
| `save_relationship(a, b, window, corr, lag)` | Simpan matriks relationship |
| `load_relationships(a, b)` | Muat relationship |
| `save_corporate_action(record)` | Simpan aksi korporasi |
| `load_corporate_actions(ticker)` | Muat aksi korporasi per ticker |
| `update_source_health(source, status)` | Upsert status sumber data |
| `get_source_health()` | Status semua sumber |
| `audit(event_type, payload, actor)` | Tulis audit log |

Audit log adalah komponen kritis untuk traceability. Setiap keputusan, trade, dan event data dicatat dengan timestamp UTC.

---

# Bab 6: Analysis Layer

## 6.1 Ikhtisar

Analysis Layer adalah jantung sistem. Empat engine analisis masing-masing menghasilkan skor 0–100 yang digabungkan oleh Decision Engine.

## 6.2 Technical Analysis Engine

**File:** `src/trading_system/analysis/technical.py`

### 6.2.1 Indikator Teknis

| Indikator | Periode | Fungsi |
|-----------|---------|--------|
| Moving Average | 20, 50 hari | Identifikasi tren |
| ADX | 14 hari | Kekuatan tren |
| RSI | 14 hari | Momentum overbought/oversold |
| MACD | 12, 26, 9 | Konfirmasi tren dan sinyal |
| ATR | 14 hari | Volatilitas |
| Bollinger Bands | 20 hari, 2 std | Range normal harga |
| Volume SMA | 20 hari | Baseline volume |
| Volume Ratio | — | Volume relatif terhadap rata-rata |
| Volatility (annualized) | 20 hari | Rezim volatilitas |

### 6.2.2 Klasifikasi Tren

- **Uptrend:** MA20 > MA50 dan close > MA20
- **Downtrend:** MA20 < MA50 dan close < MA20
- **Sideways:** Kondisi lainnya

### 6.2.3 Volume Profile

Menghitung distribusi volume berdasarkan harga close menggunakan histogram 10 bin:

- **POC (Point of Control):** Harga dengan volume tertinggi
- **VAH (Value Area High):** Batas atas 70% volume
- **VAL (Value Area Low):** Batas bawah 30% volume

### 6.2.4 Perhitungan Skor (0–100)

| Komponen | Logika | Range |
|----------|--------|-------|
| Trend | Uptrend=25, Sideways=12, Downtrend=0 | 0–25 |
| RSI | (RSI - 30) * (25/40), clamped 0–25 | 0–25 |
| MACD | MACD > Signal = 25, else 0 | 0–25 |
| Volatility | max(0, 25 - vol*100) | 0–25 |
| Volume | min(25, vol_ratio * 12.5) | 0–25 |

## 6.3 Fundamental Analysis Engine

**File:** `src/trading_system/analysis/fundamental.py`

### 6.3.1 Rasio yang Dihitung

**Valuation:** PER, PBV, PS, Dividend Yield (dari `t.info`)

**Profitability:** ROE, ROA, Gross/Operating/Net Margin (dari `t.info`)

**Leverage:** DER, Debt-to-Asset (dari `t.balance_sheet` dengan pencocokan kata kunci fuzzy)

**Growth:** Revenue Growth, EPS Growth (dari `t.info`)

### 6.3.2 Perhitungan Skor (0–100)

| Komponen | Logika | Range |
|----------|--------|-------|
| PER | min(25, max(0, 25 - PER/5)) | 0–25 |
| PBV | min(25, max(0, 25 - PBV/0.4)) | 0–25 |
| ROE | min(25, ROE) | 0–25 |
| DER | max(0, 25 - DER*25) | 0–25 |
| Growth | min(25, max(0, 12.5 + avg(eps_g, rev_g))) | 0–25 |

Jika data tidak tersedia (umum untuk saham .JK), komponen diisi nilai netral 12.5 dan status menjadi `"warning"`.

## 6.4 Macro Economic Engine

**File:** `src/trading_system/analysis/macro.py`

### 6.4.1 Klasifikasi Rezim

| Rezim | Kondisi | Dampak |
|-------|---------|--------|
| Tightening | US10Y naik | Tekanan valuasi |
| Easing | US10Y turun | Dukungan valuasi |
| Growth | Oil naik, USD/IDR turun | Pertumbuhan ekonomi |
| Slowdown | Oil turun, USD/IDR naik | Perlambatan ekonomi |
| Neutral | Kondisi lainnya | Tidak ada sinyal kuat |

### 6.4.2 Perhitungan Skor (0–100)

| Komponen | Logika | Range |
|----------|--------|-------|
| US10Y | max(0, 25 - yield * 2.5) | 0–25 |
| Gold | 25 jika chg < 5%, 12.5 jika < 10%, 0 jika >= 10% | 0–25 |
| Oil | 25 jika 60–90, else 15 | 0–25 |
| USD/IDR | 25 jika chg < 0, else 12.5 | 0–25 |

## 6.5 Global Market Engine

**File:** `src/trading_system/analysis/global_market.py`

### 6.5.1 Metodologi

Untuk setiap dari 7 indeks global: hitung MA50 dan MA200, lalu periksa apakah close berada di atas masing-masing.

### 6.5.2 Perhitungan Skor (0–100)

| Komponen | Logika | Range |
|----------|--------|-------|
| Above MA50 | (jumlah indeks di atas MA50 / total) * 50 | 0–50 |
| Above MA200 | (jumlah indeks di atas MA200 / total) * 50 | 0–50 |

Skor tinggi menunjukkan risk appetite global positif, mendukung pasar emerging markets seperti Indonesia.

---

# Bab 7: Intelligence Layer

## 7.1 Market Relationship Engine

**File:** `src/trading_system/intelligence/relationship.py`

### 7.1.1 Tujuan

Menghitung rolling correlation dan lag analysis antara saham dengan aset global dan makroekonomi. Membantu memahami seberapa besar saham dipengaruhi pasar global.

### 7.1.2 Metodologi

**Rolling Correlation:** Korelasi Pearson antara return harian saham dan aset pembanding, window default 60 hari.

**Lag Analysis:** Menguji lag -5 hingga +5 hari untuk menemukan lag dengan korelasi tertinggi. Mengidentifikasi apakah aset global memimpin (leading) atau mengikuti (lagging).

### 7.1.3 Output

```json
{
  "status": "ok",
  "engine": "relationship",
  "score": 45.67,
  "window": 60,
  "relationships": [
    {"asset": "SP500", "ticker": "^GSPC", "correlation": 0.32, "lag": 0},
    {"asset": "GOLD", "ticker": "GC=F", "correlation": -0.15, "lag": 2}
  ]
}
```

**Influence Score** = rata-rata |correlation| * 100. Skor tinggi = sangat dipengaruhi pasar global.

### 7.1.4 Aset Pembanding

- 7 indeks global (S&P 500, Nasdaq, Dow, Hang Seng, Nikkei, FTSE, DAX)
- 5 proxy makro (US10Y, Gold, Oil, USD/IDR, DXY)
- 1 benchmark (IHSG)

Total 13 aset pembanding.

## 7.2 Corporate Action Engine

**File:** `src/trading_system/corporate/actions.py`

### 7.2.1 Jenis Aksi Korporasi

| Jenis | Sumber | Unit |
|-------|--------|------|
| Stock Split | `t.splits` | Rasio (mis. 2:1 = 2.0) |
| Dividend | `t.dividends` | IDR per share (untuk .JK) |

### 7.2.2 Adjustment Factor

Method `compute_adjustment_factor(ticker)`:

- **Split:** Harga sebelum ex-date dikalikan rasio split.
- **Dividend:** Harga sebelum ex-date disesuaikan: `price / (price - dividend)`.

Hasil: DataFrame dengan `adj_factor` dan `adj_close` untuk analisis historis akuntable.

---

# Bab 8: Sentiment Engine

**File:** `src/trading_system/sentiment/engine.py`

## 8.1 Tujuan

Mengukur sentimen pasar. Saat ini placeholder yang menggunakan perubahan harga dan volume sebagai proxy sentimen.

## 8.2 Metodologi Proxy

**Price Score (0–25):** Rata-rata return 5 hari terakhir:

```
price_score = max(0, min(25, 12.5 + avg_return * 500))
```

**Volume Score (0–25):** Rasio volume 5 hari vs 20 hari:

```
vol_ratio = avg_volume_5d / avg_volume_20d
volume_score = min(25, vol_ratio * 12.5)
```

## 8.3 Output

```json
{
  "status": "ok",
  "engine": "sentiment",
  "score": 62.50,
  "sentiment": 0.25,
  "breakdown": {
    "price_score": 18.75,
    "volume_score": 15.00
  }
}
```

`sentiment` berkisar -1 (bearish) hingga +1 (bullish). `score` = (sentiment + 1) * 50.

---

# Bab 9: Risk Engine

**File:** `src/trading_system/risk/engine.py`

## 9.1 Tujuan

Menghitung ukuran posisi, stop loss, take profit, dan risk flags berdasarkan volatilitas dan likuiditas. Risk Engine wajib berjalan sebelum Decision Engine menghasilkan rekomendasi.

## 9.2 Perhitungan ATR

Average True Range (ATR) dihitung dengan periode 14 hari:

```
TR = max(high - low, |high - close_prev|, |low - close_prev|)
ATR = rolling_mean(TR, 14)
```

## 9.3 Position Sizing

Metode **fixed fractional** dengan target risk 1% dari modal per trade:

```
stop_distance = 1.5 * ATR
stop_loss = last_price - stop_distance
take_profit = last_price + 2 * stop_distance    # Risk-reward ratio 1:2

risk_amount = capital * 0.01
position_value = risk_amount / (stop_distance / last_price)
position_size = min(position_value / capital, 0.10)    # Maks 10% modal
```

## 9.4 Likuiditas dan Slippage

```
adv_value = avg_daily_volume * last_price
target_value = position_size * capital
```

Jika `target_value > adv_value * 1%`:
- Slippage dinaikkan dari 5 bps ke 20 bps
- Flag `LIQUIDITY_LOW` ditambahkan

Jika volatilitas annualized > 50%:
- Flag `HIGH_VOLATILITY` ditambahkan

## 9.5 Output

```json
{
  "status": "ok",
  "engine": "risk",
  "ticker": "BBCA.JK",
  "last_price": 8750.00,
  "atr": 125.50,
  "position_size": 0.0850,
  "stop_loss": 8561.75,
  "take_profit": 9126.50,
  "slippage": 0.0005,
  "risk_flags": [],
  "avg_daily_volume": 12500000
}
```

---

# Bab 10: Portfolio Engine

**File:** `src/trading_system/portfolio/engine.py`

## 10.1 Tujuan

Mengelola alokasi modal berdasarkan rekomendasi BUY/HOLD/SELL. Saat ini implementasi minimal: hanya memproses rekomendasi BUY.

## 10.2 Method `current_positions()`

Mengembalikan DataFrame posisi saat ini. Sementara hardcoded sebagai cash only. Nantinya akan mengambil dari tabel `positions` di database.

## 10.3 Method `generate_orders(recommendation)`

Hanya memproses rekomendasi dengan `action == "BUY"`:

1. Mengambil `position_size` dari rekomendasi.
2. Menghitung `capital_alloc = cash * position_size`.
3. Mengambil `entry_price_range` dan menghitung `mid_price`.
4. Menghitung `shares = int(capital_alloc // mid_price)`.
5. Jika shares <= 0, tidak ada order.
6. Mengembalikan list berisi satu order dict dengan `ticker`, `action`, `shares`, `target_price`, `order_value`.

---

# Bab 11: Execution Engine

**File:** `src/trading_system/execution/engine.py`

## 11.1 Tujuan

Menghitung biaya transaksi realistis dan memeriksa kelayakan order untuk eksekusi.

## 11.2 Komponen Biaya

| Komponen | Beli | Jual |
|----------|------|------|
| Broker fee | 0.15% | 0.15% |
| Levy bursa | 0.00043% | 0.00043% |
| PPh final | — | 0.1% |

## 11.3 Method `compute_fees(order_value, action)`

Menghitung breakdown biaya:

```json
{
  "brokerage": 1500000.00,
  "levy": 4300.00,
  "tax": 1000000.00,    // hanya untuk sell
  "total": 2504300.00
}
```

## 11.4 Method `estimate_slippage(order_value, avg_daily_value)`

Slippage dinamis berdasarkan ukuran order relatif terhadap avg daily value:

| Rasio order/ADV | Slippage |
|-----------------|----------|
| < 0.1% | 0.05% (default) |
| 0.1%–1% | 0.10% (2x default) |
| > 1% | 0.20% (4x default) |

## 11.5 Method `simulate_fill(order, last_price, avg_daily_value)`

Simulasi eksekusi order:

1. Estimasi slippage berdasarkan ukuran order.
2. Hitung fill price: `last_price * (1 + slippage)` untuk buy, `last_price * (1 - slippage)` untuk sell.
3. Hitung fees.
4. Hitung net value (gross + fees untuk buy, gross - fees untuk sell).

## 11.6 Method `check_feasibility(order, cash, avg_daily_value)`

Memeriksa apakah modal cukup untuk eksekusi order:

```
total_cost = order_value * (1 + buy_fee + levy + slippage)
feasible = cash >= total_cost
```

---

# Bab 12: Decision Engine

**File:** `src/trading_system/decision/engine.py`

## 12.1 Tujuan

Menggabungkan skor dari semua engine analisis menjadi rekomendasi yang dapat dieksekusi. Ini adalah engine terpenting dalam sistem karena menjadi titik konvergensi semua analisis.

## 12.2 Bobot Default

```python
DEFAULT_WEIGHTS = {
    "technical": 0.20,
    "fundamental": 0.25,
    "macro": 0.15,
    "global": 0.15,
    "relationship": 0.10,
    "sentiment": 0.15,
}
```

Fundamental memiliki bobot tertinggi (25%) karena untuk investasi saham jangka menengah, kesehatan fundamental perusahaan adalah faktor paling penting. Technical (20%) menjadi konfirmator timing.

## 12.3 Regime Filter

Method `apply_regime_filter(scores, macro_regime)` menyesuaikan skor berdasarkan rezim makroekonomi:

| Rezim | Penyesuaian |
|-------|-------------|
| Tightening | macro * 0.8, technical * 0.9 |
| Easing | macro * 1.1 (max 100), fundamental * 1.05 (max 100) |
| Lainnya | Tidak ada penyesuaian |

## 12.4 Perhitungan Conviction Score

```
conviction = sum(score[k] * weight[k] for k in weights if k in scores) / sum(weight[k])
```

Weighted average dari semua skor yang tersedia, hanya menggunakan bobot untuk engine yang memiliki skor.

## 12.5 Logika Keputusan

Method `decide_action(conviction, risk_flags)`:

```
Jika HIGH_VOLATILITY atau LIQUIDITY_LOW dalam risk_flags:
    Jika conviction < 60: AVOID
Jika conviction >= 70: BUY
Jika conviction >= 55: WATCHLIST
Jika conviction >= 40: HOLD
Jika conviction < 40: AVOID
```

## 12.6 Output Rekomendasi

```json
{
  "recommendation_id": "BBCA.JK_2026-07-30T11:23:45Z",
  "ticker": "BBCA.JK",
  "action": "BUY",
  "conviction_score": 72.50,
  "position_size": 0.085,
  "entry_price_range": [8662.50, 8837.50],
  "stop_loss": 8561.75,
  "take_profit": 9126.50,
  "expected_hold_period": "1-3 months",
  "risk_flags": [],
  "contributing_scores": {
    "technical": 68.0,
    "fundamental": 75.0,
    "macro": 62.0,
    "global": 70.0,
    "relationship": 45.67,
    "sentiment": 62.5
  },
  "created_at": "2026-07-30T11:23:45Z"
}
```

Setiap rekomendasi mencatat audit log `decision.recommendation.created`.

---

# Bab 13: Explainable AI (XAI) Engine

**File:** `src/trading_system/xai/engine.py`

## 13.1 Tujuan

Menghasilkan narasi penjelasan untuk setiap rekomendasi. Ini memastikan prinsip **Explainable** terpenuhi — pengguna tidak hanya menerima rekomendasi, tetapi juga memahami mengapa.

## 13.2 Method `explain(ticker, recommendation)`

Menerima dictionary rekomendasi dari Decision Engine dan menghasilkan:

1. **Narrative** — Teks penjelasan natural language yang menyebutkan action, conviction score, faktor paling mendukung, dan faktor paling menahan.

2. **Top Factors** — Daftar 3 faktor dengan skor tertinggi, diurutkan descending.

3. **Confidence Interval** — Estimasi sederhana: `[conviction - 10, conviction + 10]`, clamped 0–100.

4. **Risk Summary** — Daftar risk flags dari Risk Engine, atau `"No critical risk flags"` jika kosong.

5. **Counter Scenarios** — Dua skenario alternatif yang dapat mengubah rekomendasi:
   - "Jika USD/IDR melemah 5%, fundamental score bisa turun dan stop loss perlu diperketat."
   - "Jika IHSG tumbuh 2% dalam seminggu, conviction bisa naik ke level BUY."

## 13.3 Output

```json
{
  "status": "ok",
  "ticker": "BBCA.JK",
  "action": "BUY",
  "narrative": "Rekomendasi BUY untuk BBCA.JK dibentuk dengan conviction 72.5. Faktor paling mendukung adalah fundamental (score: 75.0). Faktor paling menahan adalah relationship (score: 45.67).",
  "top_factors": [["fundamental", 75.0], ["technical", 68.0], ["global", 70.0]],
  "confidence_interval": [62.5, 82.5],
  "risk_summary": ["No critical risk flags"],
  "counter_scenarios": [
    "Jika USD/IDR melemah 5%, fundamental score bisa turun...",
    "Jika IHSG tumbuh 2% dalam seminggu, conviction bisa naik..."
  ]
}
```

---

# Bab 14: AI Learning Engine

**File:** `src/trading_system/ai_learning/engine.py`

## 14.1 Tujuan

Saat ini merupakan placeholder yang mengembalikan default factor weights dan statistik sederhana. Nantinya akan melakukan retraining bobot faktor berdasarkan forward return data.

## 14.2 Method `get_factor_weights(ticker, regime)`

Mengembalikan `DEFAULT_WEIGHTS` dari Decision Engine. Nantinya akan mengembalikan bobot yang dioptimalkan berdasarkan histori performa per rezim pasar.

## 14.3 Method `feature_importance(scores)`

Menghitung importance relatif setiap faktor:

```
importance[factor] = score[factor] / sum(all scores)
```

Mengembalikan list dict `{"factor": k, "importance": v}`.

## 14.4 Roadmap AI Learning

- **Tahap 1 (saat ini):** Default weights, feature importance sederhana
- **Tahap 2:** Rolling regression untuk optimasi bobot per rezim
- **Tahap 3:** Walk-forward optimization dengan cross-validation
- **Tahap 4:** Bayesian updating untuk adaptasi real-time

---

# Bab 15: Paper Trading Engine

**File:** `src/trading_system/paper_trading/engine.py`

## 15.1 Tujuan

Mensimulasikan order dari rekomendasi dengan harga pasar saat ini, menghitung fill price, biaya, dan PnL awal. Ini adalah jembatan antara rekomendasi dan eksekusi nyata.

## 15.2 Method `simulate(ticker)`

Alur simulasi:

1. **Decision Engine** menghasilkan rekomendasi untuk ticker.
2. **Portfolio Engine** menghasilkan order dari rekomendasi (hanya untuk BUY).
3. Jika tidak ada order (bukan BUY atau data tidak cukup), kembalikan pesan.
4. Ambil harga terakhir dan avg daily volume dari OHLCV.
5. **Execution Engine** memeriksa feasibility order.
6. **Execution Engine** mensimulasikan fill (slippage, fees, net value).
7. Kembalikan hasil lengkap dengan timestamp.

## 15.3 Output

```json
{
  "status": "ok",
  "ticker": "BBCA.JK",
  "recommendation": { ... },
  "order": {
    "ticker": "BBCA.JK",
    "action": "BUY",
    "shares": 968,
    "target_price": 8750.00,
    "order_value": 84700000
  },
  "feasibility": {
    "feasible": true,
    "required_cash": 84827310.50,
    "available_cash": 1000000000,
    "slippage_pct": 0.05
  },
  "simulated_fill": {
    "ticker": "BBCA.JK",
    "action": "BUY",
    "shares": 968,
    "fill_price": 8754.38,
    "gross_value": 84742438.00,
    "fees": { "brokerage": 127113.00, "levy": 364.00, "tax": 0, "total": 127477.00 },
    "net_value": 84869915.00,
    "slippage_pct": 0.05
  },
  "timestamp": "2026-07-30T11:23:45Z"
}
```

---

# Bab 16: Monitoring Engine

**File:** `src/trading_system/monitoring/engine.py`

## 16.1 Tujuan

Health check sederhana seluruh engine dan sumber data. Memberikan gambaran menyeluruh tentang status sistem.

## 16.2 Method `health()`

Mengumpulkan:

1. **Source Health** — Status semua sumber data dari `source_health` table.
2. **Tickers in DB** — Daftar ticker yang tersimpan.
3. **Score Count** — Jumlah skor yang telah dihitung.
4. **Alerts** — Daftar sumber dengan status bukan `"ok"`.

## 16.3 Output

```json
{
  "status": "ok",
  "timestamp": "2026-07-30T11:23:45Z",
  "sources": [
    {"source": "yahoo_finance", "last_success": "2026-07-30T10:00:00Z", "status": "ok"}
  ],
  "tickers_in_db": ["BBCA.JK", "TLKM.JK", "^JKSE", "^GSPC"],
  "score_count": 42,
  "alerts": []
}
```

---

# Bab 17: Backtesting Engine

**File:** `src/trading_system/backtest/engine.py`

## 17.1 Tujuan

Menguji strategi trading secara historis dengan biaya transaksi realistis. Backtest adalah fondasi dari prinsip **Backtestable First**.

## 17.2 Cost Model

Class `CostModel` mendefinisikan struktur biaya:

```python
buy_cost_pct = buy_fee + levy + slippage    # 0.15% + 0.00043% + 0.05% = 0.20043%
sell_cost_pct = sell_fee + levy + slippage  # 0.25% + 0.00043% + 0.05% = 0.30043%
```

## 17.3 Method `run(ticker, strategy, start, end, initial_capital, cost_model)`

Alur backtest event-driven:

1. Muat OHLCV dari storage.
2. Generate sinyal dengan `strategy.generate_signals(df)`.
3. Iterasi setiap baris (event-driven):
   - Hitung equity: `capital + position * price`.
   - Jika sinyal BUY dan tidak ada posisi: beli dengan slippage, gunakan 99% modal.
   - Jika sinyal SELL dan ada posisi: jual dengan slippage, hitung PnL.
   - Catat setiap trade ke audit log.
4. Force close posisi yang masih terbuka di akhir periode.
5. Hitung benchmark equity curve (IHSG).
6. Panggil `compute_metrics()` untuk metrik lengkap.

## 17.4 Strategi

**File:** `src/trading_system/backtest/strategies.py`

### BuyAndHold

Beli di hari pertama (signal=1), jual di hari terakhir (signal=-1). Strategi benchmark paling sederhana.

### MovingAverageCrossover

- Fast MA (default 20) > Slow MA (default 50) → BUY
- Fast MA < Slow MA → SELL
- Sinyal hanya pada crossing (perubahan dari tidak terpenuhi ke terpenuhi)

## 17.5 Metrik Kinerja

**File:** `src/trading_system/backtest/metrics.py`

Function `compute_metrics(trade_history, equity_curve, benchmark)`:

| Metrik | Rumus | Interpretasi |
|--------|-------|--------------|
| Total Return | `equity[-1] / equity[0] - 1` | Return total |
| CAGR | `(equity[-1] / equity[0])^(1/years) - 1` | Return tahunan |
| Max Drawdown | `min((equity - cummax) / cummax)` | Penurunan terbesar |
| Sharpe Ratio | `excess.mean() / returns.std() * sqrt(252)` | Risk-adjusted return |
| Sortino Ratio | `excess.mean() / downside.std() * sqrt(252)` | Sharpe dengan downside only |
| Calmar Ratio | `CAGR / |max_drawdown|` | Return vs drawdown |
| Win Rate | `wins / total_trades` | Persentase trade profit |
| Profit Factor | `wins.sum() / |losses.sum()|` | Profit vs loss |
| Average Win | `wins.mean()` | Rata-rata profit per trade |
| Average Loss | `losses.mean()` | Rata-rata loss per trade |
| Expectancy | `trades.pnl.mean()` | Expected value per trade |
| Volatility | `returns.std() * sqrt(252)` | Volatilitas tahunan |
| Beta | `cov(returns, benchmark) / var(benchmark)` | Sensitivitas ke pasar |
| Alpha | `returns.mean() - rf - beta * (benchmark.mean() - rf)` | Excess return |
| Exposure Time | `n_days / 252` | Waktu di pasar |

Risk-free rate default: 5% per tahun (asumsi SBN).

---

# Bab 18: Analysis Pipeline

**File:** `src/trading_system/analysis/pipeline.py`

## 18.1 Tujuan

Orkestrasi eksekusi semua engine analisis secara berurutan. Pipeline memastikan data OHLCV tersedia sebelum analisis, dan menyimpan semua skor ke database.

## 18.2 Class AnalysisPipeline

Menginisialisasi semua engine:

```python
self.technical = TechnicalAnalysisEngine()
self.fundamental = FundamentalAnalysisEngine()
self.macro = MacroEconomicEngine(self.storage)
self.global_market = GlobalMarketEngine(self.storage)
self.relationship = MarketRelationshipEngine(self.storage)
self.corporate = CorporateActionEngine(self.storage)
self.sentiment = SentimentEngine(self.storage)
```

## 18.3 Method `ensure_ohlcv(ticker, period)`

Memastikan data OHLCV tersedia:
1. Cek apakah data sudah ada di storage.
2. Jika belum, fetch dari Yahoo Finance.
3. Validasi dan simpan.
4. Kembalikan `True` jika berhasil, `False` jika gagal.

## 18.4 Method `compute(ticker, period)`

Alur komputasi:

1. **Ensure OHLCV** — Pastikan data tersedia.
2. **Technical** — Load OHLCV ke engine, panggil `analyze()`.
3. **Fundamental** — Fetch data fundamental, panggil `analyze()`.
4. **Macro** — Panggil `analyze(period)`.
5. **Global** — Panggil `analyze(period)`.
6. **Relationship** — Panggil `compute(ticker)`.
7. **Corporate** — Panggil `fetch(ticker)`.
8. **Sentiment** — Panggil `compute(ticker)`.
9. **Save Scores** — Untuk setiap engine dengan status ok/warning dan score tidak None, simpan ke database.
10. Kembalikan dictionary dengan semua skor dan detail.

## 18.5 Output

```json
{
  "status": "ok",
  "ticker": "BBCA.JK",
  "as_of": "2026-07-30T11:23:45Z",
  "scores": {
    "technical": 68.0,
    "fundamental": 75.0,
    "macro": 62.0,
    "global": 70.0,
    "relationship": 45.67,
    "sentiment": 62.5
  },
  "details": {
    "technical": { "status": "ok", "score": 68.0, "regime": "uptrend", ... },
    "fundamental": { "status": "ok", "score": 75.0, "ratios": {...}, ... },
    "macro": { "status": "ok", "score": 62.0, "regime": "easing", ... },
    "global": { "status": "ok", "score": 70.0, ... },
    "relationship": { "status": "ok", "score": 45.67, ... },
    "sentiment": { "status": "ok", "score": 62.5, ... }
  }
}
```

---

# Bab 19: API Layer (FastAPI)

**File:** `src/trading_system/api/app.py`

## 19.1 Ikhtisar

FastAPI menyediakan REST API dan WebSocket untuk komunikasi antara backend dan frontend. API berjalan di port 8000 dengan Uvicorn ASGI server.

## 19.2 Endpoint REST

| Method | Path | Fungsi |
|--------|------|--------|
| GET | `/` | Status dan versi |
| GET | `/api/health` | Health check sumber data |
| GET | `/api/data/{category}` | Ambil data OHLCV per ticker |
| POST | `/api/fetch` | Fetch dan simpan data dari Yahoo Finance |
| GET | `/api/scores/{ticker}` | Ambil skor tersimpan per ticker |
| POST | `/api/scores/compute` | Hitung skor semua engine untuk ticker |
| GET | `/api/corporate/{ticker}` | Fetch aksi korporasi |
| GET | `/api/relationship/{ticker}` | Hitung relationship dengan aset global |
| GET | `/api/recommend/{ticker}` | Rekomendasi BUY/HOLD/AVOID |
| POST | `/api/recommend` | Rekomendasi dengan custom weights |
| GET | `/api/explain/{ticker}` | Penjelasan rekomendasi (XAI) |
| POST | `/api/paper-trade` | Simulasi paper trade |
| GET | `/api/monitor` | Status sistem lengkap |
| GET | `/api/factor-weights/{ticker}` | Factor weights dari AI Learning |
| POST | `/api/backtest` | Jalankan backtest |
| GET | `/api/engines` | Status semua engine terdaftar |

## 19.3 WebSocket

| Path | Fungsi |
|------|--------|
| `ws://host:8000/ws/engines` | Real-time engine status, update setiap 5 detik |

WebSocket mengirimkan `_build_engines_status()` setiap 5 detik. Frontend Engine Monitor menggunakan WebSocket ini untuk menampilkan status real-time.

## 19.4 Engine Registry

`ENGINE_REGISTRY` adalah list berisi metadata semua engine terdaftar:

```python
ENGINE_REGISTRY = [
    {"name": "technical", "module": "trading_system.analysis.technical", "cls": "TechnicalAnalysisEngine"},
    {"name": "fundamental", "module": "trading_system.analysis.fundamental", "cls": "FundamentalAnalysisEngine"},
    {"name": "macro", "module": "trading_system.analysis.macro", "cls": "MacroEconomicEngine"},
    {"name": "global_market", "module": "trading_system.analysis.global_market", "cls": "GlobalMarketEngine"},
    {"name": "relationship", "module": "trading_system.intelligence.relationship", "cls": "MarketRelationshipEngine"},
    {"name": "sentiment", "module": "trading_system.sentiment.engine", "cls": "SentimentEngine"},
    {"name": "corporate", "module": "trading_system.corporate.actions", "cls": "CorporateActionEngine"},
    {"name": "decision", "module": "trading_system.decision.engine", "cls": "DecisionEngine"},
    {"name": "xai", "module": "trading_system.xai.engine", "cls": "ExplainableAIEngine"},
    {"name": "backtest", "module": "trading_system.backtest.engine", "cls": "BacktestEngine"},
    {"name": "paper_trading", "module": "trading_system.paper_trading.engine", "cls": "PaperTradingEngine"},
    {"name": "monitoring", "module": "trading_system.monitoring.engine", "cls": "MonitoringEngine"},
    {"name": "ai_learning", "module": "trading_system.ai_learning.engine", "cls": "AILearningEngine"},
    {"name": "risk", "module": "trading_system.risk.engine", "cls": "RiskEngine"},
    {"name": "execution", "module": "trading_system.execution.engine", "cls": "ExecutionEngine"},
]
```

## 19.5 Function `_build_engines_status()`

Untuk setiap engine di registry:

1. Import modul secara dinamis dengan `importlib.import_module()`.
2. Instantiate class (dengan atau tanpa `storage` parameter).
3. Cek status: `healthy` (ada skor), `idle` (belum pernah dijalankan), `warning` (monitoring tidak ok), atau `error` (exception).
4. Catat latency dalam milidetik.
5. Ambil latest score dan sample ticker jika tersedia.

## 19.6 Proxy Configuration

Frontend Next.js melakukan proxy request API ke backend melalui `next.config.ts`:

```typescript
async rewrites() {
  return [
    { source: "/api/:path*", destination: "http://127.0.0.1:8000/api/:path*" },
  ];
}
```

Ini memungkinkan frontend dan backend berjalan di port berbeda tanpa CORS issues.

---

# Bab 20: Frontend

## 20.1 Ikhtisar Teknologi

Frontend dibangun dengan Next.js 16 (App Router), React 19, TypeScript, dan TailwindCSS v4. Tema visual: **terminal/trading desk** dengan latar gelap (zinc-950) dan font monospace.

## 20.2 Struktur Halaman

| Halaman | Path | Fungsi |
|---------|------|--------|
| Home | `/` | Redirect ke `/dashboard` |
| Dashboard | `/dashboard` | Analisis saham lengkap |
| Engine Monitor | `/engines` | Monitor status semua engine real-time |

## 20.3 Komponen

### TerminalLayout

**File:** `frontend/app/components/TerminalLayout.tsx`

Layout bersama dengan:
- Header: Logo "TS-MON", status LIVE, ticker, jam, navigasi
- Sidebar: Navigation (Dashboard, Engine Monitor), Market overview
- Main content area

### PriceChart

**File:** `frontend/app/components/PriceChart.tsx`

Candlestick chart menggunakan TradingView Lightweight Charts:
- Warna hijau untuk bullish, merah untuk bearish
- Auto-resize dengan event listener
- Auto-fit content ke viewport

## 20.4 Dashboard Page

**File:** `frontend/app/dashboard/page.tsx`

Halaman utama yang menampilkan:

1. **Input ticker** — Text input dengan tombol ANALYZE
2. **Stat cards** — 8 kartu: Ticker, Last Price, Daily Change, Change %, Today's Range, 52W Range, Action, Conviction
3. **Price chart** — Candlestick chart (2/3 lebar)
4. **Factor scores** — Horizontal bar chart dengan warna: hijah (>=70), kuning (40-69), merah (<40)
5. **Recommendation panel** — Position size, entry range, stop loss, take profit, risk flags
6. **Explanation panel** — Narasi XAI, top factors, confidence interval
7. **System health** — API status, tickers in DB, scores computed, active alerts
8. **Ticker chips** — Klik untuk switch ticker
9. **Footer** — Status ringkas dan render timestamp

Dashboard melakukan 5 API call paralel saat ticker berubah:
- `/api/data/ohlcv?ticker=...`
- `/api/scores/...`
- `/api/recommend/...`
- `/api/explain/...`
- `/api/monitor`

## 20.5 Engine Monitor Page

**File:** `frontend/app/engines/page.tsx`

Monitor real-time dengan WebSocket:

1. **Koneksi WebSocket** ke `ws://host:8000/ws/engines` dengan auto-reconnect setiap 3 detik.
2. **Grid engine tiles** — Setiap engine ditampilkan sebagai kartu dengan:
   - Status dot (hijau=healthy, kuning=idle, oranye=warning, merah=error)
   - Latency dalam ms
   - Last run time
   - Latest score (jika ada)
3. **Detail panel** — Klik engine untuk melihat detail
4. **System summary** — Total engines, healthy count, error count
5. **Connection status** — WS status (connecting/open/closed/error)

## 20.6 Styling

**File:** `frontend/app/globals.css`

Menggunakan TailwindCSS v4 dengan import `@import "tailwindcss"`. Mendukung dark mode otomatis. Font: Geist Sans dan Geist Mono dari Vercel.

---

# Bab 21: CLI (Command-Line Interface)

**File:** `src/trading_system/cli.py`

## 21.1 Ikhtisar

CLI menyediakan akses ke semua fungsi sistem dari terminal. Menggunakan `argparse` dengan subcommands.

## 21.2 Perintah Tersedia

| Perintah | Argumen | Fungsi |
|----------|---------|--------|
| `fetch` | `tickers...`, `--period` | Fetch dan simpan data OHLCV |
| `backtest` | `ticker`, `--strategy`, `--capital` | Jalankan backtest |
| `list` | — | Daftar ticker di database |
| `compute-scores` | `ticker`, `--period` | Hitung skor semua engine |
| `corporate-actions` | `ticker` | Fetch aksi korporasi |
| `relationship` | `ticker`, `--window` | Hitung relationship |
| `recommend` | `ticker`, `--capital` | Rekomendasi BUY/HOLD/AVOID |
| `explain` | `ticker` | Penjelasan rekomendasi |
| `monitor` | — | Health check sistem |
| `paper-trade` | `ticker`, `--capital` | Simulasi paper trade |

## 21.3 Contoh Penggunaan

```bash
# Fetch data
python -m trading_system.cli fetch BBCA.JK TLKM.JK --period 2y

# Compute scores
python -m trading_system.cli compute-scores BBCA.JK

# Backtest
python -m trading_system.cli backtest BBCA.JK --strategy ma_crossover

# Rekomendasi
python -m trading_system.cli recommend BBCA.JK

# Penjelasan
python -m trading_system.cli explain BBCA.JK

# Paper trade
python -m trading_system.cli paper-trade BBCA.JK --capital 500000000

# Monitor
python -m trading_system.cli monitor

# Corporate actions
python -m trading_system.cli corporate-actions BBCA.JK

# Relationship
python -m trading_system.cli relationship BBCA.JK --window 90
```

---

# Bab 22: Testing

## 22.1 Ikhtisar

Testing menggunakan Pytest dengan Playwright untuk end-to-end testing. Test berada di `tests/e2e/`.

## 22.2 Test Dashboard

**File:** `tests/e2e/test_dashboard.py`

Empat test case:

1. **`test_dashboard_loads`** — Verifikasi dashboard termuat dengan input default BBCA.JK
2. **`test_analyze_default_ticker`** — Klik ANALYZE, tunggu rekomendasi (BUY/HOLD/WATCHLIST/AVOID), verifikasi bar chart muncul
3. **`test_change_ticker_and_analyze`** — Ganti ke TLKM.JK, verifikasi update
4. **`test_api_proxy_reachable`** — Verifikasi footer menampilkan data dari API

Setiap test mengambil screenshot untuk dokumentasi visual di `tests/e2e/screenshots/`.

## 22.3 Record Demo

**File:** `tests/e2e/record_demo.py`

Script Playwright untuk merekam sesi demo sebagai video:
1. Buka dashboard
2. Analyze BBCA.JK
3. Switch ke TLKM.JK
4. Simpan video di `tests/e2e/demo_gif/`

## 22.4 Menjalankan Test

```bash
# Pastikan backend dan frontend berjalan
./run_all.sh

# Jalankan test E2E
cd /opt/lampp/htdocs/global
source venv/bin/activate
pytest tests/e2e/test_dashboard.py -v

# Rekam demo
python tests/e2e/record_demo.py
```

---

# Bab 23: Deployment dan Operasional

## 23.1 Script `run_all.sh`

**File:** `run_all.sh`

Script untuk menjalankan backend dan frontend sekaligus:

1. **Stop server lama** — `pkill` untuk next-server, api/app.py, uvicorn; `fuser -k` untuk port 8000
2. **Build frontend** — `npm run build` di direktori frontend
3. **Start backend** — `nohup venv/bin/python src/trading_system/api/app.py` ke `/tmp/backend.log`
4. **Start frontend** — `nohup npm start` ke `/tmp/frontend.log`
5. **Tampilkan log** — Cetak backend dan frontend log

## 23.2 Menjalankan Manual

### Backend saja

```bash
cd /opt/lampp/htdocs/global
source venv/bin/activate
python -m trading_system.api.app
# atau
uvicorn trading_system.api.app:app --reload --host 0.0.0.0 --port 8000
```

### Frontend saja

```bash
cd /opt/lampp/htdocs/global/frontend
npm run dev    # development mode
# atau
npm run build && npm start    # production mode
```

## 23.3 Konfigurasi Port

| Komponen | Port Default |
|----------|-------------|
| Backend (FastAPI/Uvicorn) | 8000 |
| Frontend (Next.js) | 3000 (dev) / 45469 (prod) |

Frontend memproxy `/api/*` ke `http://127.0.0.1:8000/api/*` melalui Next.js rewrites.

## 23.4 Database

Database SQLite berada di `data/trading_system.db`. Tidak memerlukan server database terpisah. Untuk produksi skala besar, dapat dimigrasi ke TimescaleDB atau PostgreSQL dengan mengganti implementasi `DataStorage`.

## 23.5 Logging

- Backend: `nohup` output ke `/tmp/backend.log`
- Frontend: `nohup` output ke `/tmp/frontend.log`
- Audit log: Tabel `audit_log` di SQLite dengan timestamp UTC

---

# Bab 24: Roadmap Pengembangan

## 24.1 Peningkatan Data Source

- Integrasi dengan API Bursa Efek Indonesia (IDX) untuk data real-time
- Penambahan sumber data fundamental: Emiten, BEI, third-party data provider
- Kalender ekonomi dari ForexFactory/TradingEconomics
- Berita dan sentimen dari NewsAPI, Google News, RSS, X/Twitter

## 24.2 Peningkatan Analysis

- Indikator teknikal tambahan: Ichimoku, Williams %R, Stochastic
- Fundamental: DCF valuation, Altman Z-Score, Piotroski F-Score
- Macro: Inflasi, GDP, pengangguran dari BPS/BI
- Sentiment: NLP pada headline berita, social media sentiment

## 24.3 Peningkatan Risk & Portfolio

- Portfolio optimization (Markowitz mean-variance)
- Correlation-based position sizing
- Dynamic stop loss berdasarkan volatilitas regime
- Maximum portfolio drawdown limit

## 24.4 Peningkatan AI Learning

- Rolling regression untuk optimasi bobot per rezim
- Walk-forward optimization dengan cross-validation
- Bayesian updating untuk adaptasi real-time
- Feature engineering otomatis

## 24.5 Peningkatan Infrastructure

- Scheduler otomatis (cron/APS) untuk fetch data berkala
- Docker containerization untuk deployment
- CI/CD pipeline
- Alerting via email/Telegram untuk risk flags dan anomali

## 24.6 Peningkatan Frontend

- Halaman backtest dengan visualisasi equity curve
- Halaman portfolio dengan alokasi visual
- Halaman audit log untuk traceability
- Mobile-responsive design
- Dark/light theme toggle

---

# Lampiran A: Skema Database SQLite

**File:** `src/trading_system/data/storage.py` (variabel `SCHEMA`)

## Tabel `ohlcv`

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| ticker | TEXT | Kode saham |
| asset_class | TEXT | Kel aset (equity, index, commodity) |
| exchange | TEXT | Bursa (IDX, GLOBAL) |
| timestamp | TEXT | Waktu bar |
| timeframe | TEXT | Interval (1d, 1h, dll) |
| open | REAL | Harga buka |
| high | REAL | Harga tertinggi |
| low | REAL | Harga terendah |
| close | REAL | Harga penutupan |
| volume | REAL | Volume transaksi |
| adjusted_close | REAL | Harga adjusted |
| source | TEXT | Sumber data |
| ingested_at | TEXT | Waktu ingest |
| data_quality_score | REAL | Skor kualitas (0-100) |

Primary key: `(ticker, timestamp, timeframe)`

## Tabel `source_health`

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| source | TEXT | Nama sumber (PK) |
| last_success | TEXT | Waktu sukses terakhir |
| last_error | TEXT | Waktu error terakhir |
| status | TEXT | ok / down / degraded |

## Tabel `audit_log`

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| event_id | INTEGER | Auto-increment PK |
| event_type | TEXT | Jenis event |
| payload | TEXT | JSON payload |
| timestamp | TEXT | Waktu event |
| actor | TEXT | Aktor (system, user) |

## Tabel `scores`

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| ticker | TEXT | Kode saham |
| engine | TEXT | Nama engine |
| score | REAL | Skor (0-100) |
| breakdown | TEXT | JSON breakdown |
| as_of | TEXT | Timestamp perhitungan |

Primary key: `(ticker, engine, as_of)`

## Tabel `relationship_matrix`

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| asset_a | TEXT | Aset pertama |
| asset_b | TEXT | Aset kedua |
| window | INTEGER | Rolling window |
| correlation | REAL | Koefisien korelasi |
| lag | INTEGER | Lag optimal |
| updated_at | TEXT | Waktu update |

Primary key: `(asset_a, asset_b, window)`

## Tabel `corporate_actions`

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| ticker | TEXT | Kode saham |
| action_type | TEXT | split / dividend |
| announce_date | TEXT | Tanggal pengumuman |
| ex_date | TEXT | Tanggal ex-date |
| record_date | TEXT | Tanggal record |
| payment_date | TEXT | Tanggal pembayaran |
| value | REAL | Nilai aksi |
| unit | TEXT | Satuan (ratio, IDR_per_share) |
| source | TEXT | Sumber data |

Primary key: `(ticker, action_type, ex_date)`

## Tabel `news`

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| news_id | TEXT | ID unik (PK) |
| headline | TEXT | Judul berita |
| body | TEXT | Isi berita |
| published_at | TEXT | Waktu publikasi |
| source | TEXT | Sumber berita |
| entities | TEXT | Entitas terkait |
| topic | TEXT | Topik |
| sentiment | REAL | Skor sentimen |
| impact | REAL | Skor dampak |

---

# Lampiran B: Data Contracts (Pydantic)

**File:** `src/trading_system/data/contracts.py`

## OHLCVRecord

```python
class OHLCVRecord(BaseModel):
    ticker: str
    asset_class: str = "equity"
    exchange: str = "IDX"
    timestamp: datetime
    timeframe: str = "1d"
    open: float
    high: float
    low: float
    close: float
    volume: float
    adjusted_close: float
    source: str
    ingested_at: Optional[datetime] = None
    data_quality_score: Optional[float] = None
```

## DataSourceHealth

```python
class DataSourceHealth(BaseModel):
    source: str
    last_success: Optional[datetime] = None
    last_error: Optional[datetime] = None
    status: str = "unknown"  # ok, degraded, down
```

## DataQualityReport

```python
class DataQualityReport(BaseModel):
    record_count: int
    data_quality_score: float  # 0-100
    anomalies: list[dict[str, Any]] = []
    action: str = "accept"  # accept, flag, pause
```

---

# Lampiran C: Engine Registry Lengkap

| # | Name | Module | Class |
|---|------|--------|-------|
| 1 | technical | trading_system.analysis.technical | TechnicalAnalysisEngine |
| 2 | fundamental | trading_system.analysis.fundamental | FundamentalAnalysisEngine |
| 3 | macro | trading_system.analysis.macro | MacroEconomicEngine |
| 4 | global_market | trading_system.analysis.global_market | GlobalMarketEngine |
| 5 | relationship | trading_system.intelligence.relationship | MarketRelationshipEngine |
| 6 | sentiment | trading_system.sentiment.engine | SentimentEngine |
| 7 | corporate | trading_system.corporate.actions | CorporateActionEngine |
| 8 | decision | trading_system.decision.engine | DecisionEngine |
| 9 | xai | trading_system.xai.engine | ExplainableAIEngine |
| 10 | backtest | trading_system.backtest.engine | BacktestEngine |
| 11 | paper_trading | trading_system.paper_trading.engine | PaperTradingEngine |
| 12 | monitoring | trading_system.monitoring.engine | MonitoringEngine |
| 13 | ai_learning | trading_system.ai_learning.engine | AILearningEngine |
| 14 | risk | trading_system.risk.engine | RiskEngine |
| 15 | execution | trading_system.execution.engine | ExecutionEngine |

---

# Lampiran D: Glosarium

| Istilah | Definisi |
|---------|----------|
| ATR | Average True Range — ukuran volatilitas harga |
| ADV | Average Daily Volume — rata-rata volume harian |
| Alpha | Excess return relatif terhadap benchmark |
| Beta | Sensitivitas return saham terhadap return pasar |
| CAGR | Compound Annual Growth Rate — return tahunan compound |
| Conviction Score | Skor keyakinan 0–100 dari gabungan semua faktor |
| Cost Model | Model biaya transaksi (broker, levy, slippage, tax) |
| Drawdown | Penurunan dari puncak equity |
| IHSG | Indeks Harga Saham Gabungan (benchmark BEI) |
| MA | Moving Average — rata-rata bergerak harga |
| MACD | Moving Average Convergence Divergence |
| OHLCV | Open, High, Low, Close, Volume — data harga standar |
| POC | Point of Control — harga dengan volume tertinggi |
| PPh | Pajak Penghasilan |
| Regime | Kondisi pasar/makroekonomi (uptrend, easing, dll) |
| RSI | Relative Strength Index — indikator momentum |
| Sharpe Ratio | Return risk-adjusted relatif terhadap volatilitas |
| Slippage | Selisih antara harga order dan harga fill |
| Sortino Ratio | Sharpe ratio yang hanya mempertimbangkan downside volatility |
| VAH | Value Area High — batas atas 70% volume |
| VAL | Value Area Low — batas bawah 30% volume |
| XAI | Explainable AI — AI yang dapat dijelaskan |

---

*Dokumen ini disusun pada Juli 2026. Versi aplikasi: 0.1.0.*

*Untuk pertanyaan teknis, merujuk pada kode sumber di direktori `src/trading_system/` dan `frontend/`.*
