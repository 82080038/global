# Analisis Sumber Data — Komputer, HDD, MySQL, htdocs

> Tanggal: 1 Agustus 2026  
> Tujuan: Identifikasi semua data yang berguna untuk memperkaya database/aplikasi trading system.

---

## Ringkasan Eksekutif

Ditemukan **4 sumber data** dengan total **~1.5 juta baris** data yang bisa memperkaya sistem trading:

| Sumber | Lokasi | Ukuran | Status di Aplikasi |
|--------|--------|--------|-------------------|
| MySQL `data_pasar_modal` | localhost | 253 MB | Sebagian sudah diexport ke Parquet |
| MySQL lainnya (11 DB) | localhost | ~10 MB | Belum diintegrasikan |
| SQLite `saham.db` | `pasar_modal/data/` | 6.9 MB | Belum diintegrasikan |
| PHP App `data_pasar_modal` | htdocs | ~500 MB (incl. SQL dump) | Belum diintegrasikan |
| Python App `pasar_modal` | htdocs | ~50 MB kode ML/DL | Belum diintegrasikan |
| External HDD K: | `K:\trading_data\raw\` | 27.7 MB Parquet | Sudah diexport |

---

## 1. MySQL `data_pasar_modal` — Tabel yang Belum Diexport

### Tabel berisi data (belum diexport ke Parquet):

| Tabel | Baris | Relevansi | Prioritas |
|-------|-------|-----------|-----------|
| `chart_patterns` | 43,312 | **TINGGI** — Pola candlestick historis per saham (bullish/bearish/neutral, confidence score) | 1 |
| `saham_historical` | 13,440 | **TINGGI** — OHLCV 47 saham sejak 2000 (alternatif/complement `stock_history`) | 1 |
| `multi_asset` | 3,312 | **TINGGI** — Forex, crypto, commodity, index, bond (1,147 forex + 1,064 commodity + 597 crypto + 336 index + 168 bond) | 1 |
| `foreign_flow` | 465 | **TINGGI** — Aliran dana asing (beli/jual/net) IHSG harian | 1 |
| `fear_greed_index` | 465 | **TINGGI** — Indeks fear/greed harian (sentimen pasar) | 1 |
| `indikator_teknikal` | 465 | **SEDANG** — Indikator teknikal agregat | 2 |
| `saham` | 359 | **TINGGI** — Master data 359 saham IDX (kode, nama, sektor) | 1 |
| `stock_ipo` | 348 | **SEDANG** — Data IPO saham | 3 |
| `corporate_governance` | 208 | **SEDANG** — Tata kelola perusahaan (score, board, audit) | 2 |
| `kebijakan_regulasi` | 179 | **SEDANG** — Kebijakan moneter/fiskal/regulasi (dampak, sektor) | 2 |
| `esg_scores` | 164 | **SEDANG** — ESG score per saham (environment, social, governance) | 2 |
| `event_eksternal` | 119 | **SEDANG** — Event geopolitik, perubahan iklim (dampak market, sektor) | 2 |
| `ai_scores` | 47 | **SEDANG** — AI/ML scores historis per saham | 2 |
| `ai_alerts` | 47 | **RENDAH** — Alert AI | 3 |
| `ai_portfolio` | 93 | **RENDAH** — Rekomendasi portfolio AI | 3 |
| `pattern_analysis` | 53 | **SEDANG** — Analisis pola (winrate, reliability) | 2 |
| `stock_personality` | 11 | **SEDANG** — Profil kepribadian saham (volatility regime, trend bias, beta, liquidity score, personality label) | 2 |
| `sektor` | 11 | **RENDAH** — Master sektor | 3 |
| `blind_forecast` | 25 | **RENDAH** — Forecast blind test | 3 |
| `backtest_result` | 11 | **RENDAH** — Hasil backtest historis | 3 |
| `transaksi` | 5 | **RENDAH** — Transaksi | 3 |
| `portfolio` | 5 | **RENDAH** — Portfolio | 3 |
| `trade_journal` | 4 | **RENDAH** — Journal trading | 3 |
| `strategy_config` | 4 | **RENDAH** — Konfigurasi strategi | 3 |
| `price_alerts` | 4 | **RENDAH** — Alert harga | 3 |
| `training_log` | 4 | **RENDAH** — Log training ML | 3 |
| `ml_config` | 7 | **RENDAH** — Konfigurasi ML | 3 |
| `ai_correlation` | 7 | **RENDAH** — Korelasi AI | 3 |
| `ai_auto_trade` | 7 | **RENDAH** — Auto trade AI | 3 |
| `trader_saldo` | 6 | **RENDAH** — Saldo trader | 3 |
| `notifications` | 29 | **RENDAH** — Notifikasi | 3 |
| `saham_teknikal` | 2,614 | **SEDANG** — Indikator teknikal per saham | 2 |
| `data_fetch_log` | 2,417 | **RENDAH** — Log fetch data | 3 |
| `aksi_korporasi` | 2,540 | **SEDANG** — Sudah diexport | ✅ |
| `bursa_global` | 1,760 | **SEDANG** — Sudah diexport | ✅ |
| `komoditas` | 1,523 | **SEDANG** — Sudah diexport | ✅ |
| `berita_sentimen` | 921 | **SEDANG** — Sudah diexport | ✅ |
| `saham_fundamental` | 836 | **SEDANG** — Sudah diexport | ✅ |
| `makroekonomi` | 379 | **SEDANG** — Sudah diexport | ✅ |
| `ihsg_history` | 465 | **SEDANG** — Sudah diexport | ✅ |

### Tabel kosong (0 baris, tapi skema berguna):
`dividend`, `pattern_reliability`, `pattern_candidates`, `market_manipulation_log`, `backtest_strategy_result`, `model_performance`, `risk_config`, `advanced_features`, `data_update_status`, `valuation_cache`, `market_calendar`, `dl_predictions`, `watchlist`, `retraining_log`

---

## 2. MySQL Database Lain yang Relevan

| Database | Tabel berisi data | Relevansi |
|----------|-------------------|-----------|
| `data_ingestion` | `ohlcv_daily` (9,927 baris, 22 instruments, 2024-2026) | **SEDANG** — OHLCV dari sistem lain |
| `market_master` | `instrument` (107), `security` (85), `issuer` (56), `listing` (47), `exchange` (13) | **TINGGI** — Master data instrumen (ISIN, currency, listing date, sector, sub-sector) |
| `analytics` | `signal` (5), `model_registry` (1) | **RENDAH** |
| `governance` | `audit_log` (123), `policy` (2), `approval` (1) | **RENDAH** |
| `alert` | `alert` (3) | **RENDAH** |
| `portfolio` | `portfolio` (3) | **RENDAH** |
| `trading` | `broker` (2) | **RENDAH** |
| `ai_engine` | (empty) | — |
| `backtesting` | (empty) | — |
| `fundamental` | (empty) | — |
| `microstructure` | (empty) | — |
| `paper_trading` | (empty) | — |
| `platform` | (empty) | — |
| `risk` | (empty) | — |
| `settlement` | (empty) | — |
| `valuation` | (empty) | — |

---

## 3. SQLite `saham.db` (pasar_modal)

**Lokasi:** `C:\xampp\htdocs\pasar_modal\data\saham.db` (6.9 MB)

| Tabel | Baris | Relevansi |
|-------|-------|-----------|
| `ohlcv` | 23,851 | **TINGGI** — OHLCV data (mungkin overlap dengan MySQL) |
| `global_market_data` | 15,046 | **TINGGI** — Data bursa global |
| `macro_data` | 8,776 | **TINGGI** — Data makroekonomi |
| `instruments` | 21 | **SEDANG** — Master instrumen |
| `alembic_version` | 1 | — |
| `alternative_data` | 0 | Skema ada (alternative data) |
| `climate_data` | 0 | Skema ada (data iklim) |
| `corporate_actions` | 0 | Skema ada |
| `geopolitical_data` | 0 | Skema ada |
| `journal_entries` | 0 | Skema ada |
| `model_drift` | 0 | Skema ada (ML model drift) |
| `model_performance` | 0 | Skema ada |
| `predictions` | 0 | Skema ada |
| `red_flags` | 0 | Skema ada (flag risiko) |
| `regime_history` | 0 | Skema ada (market regime) |
| `screener_results` | 0 | Skema ada |
| `sector_metrics` | 0 | Skema ada |
| `tax_config` | 0 | Skema ada |
| `trade_recommendations` | 0 | Skema ada |
| `watchlist` | 0 | Skema ada |

---

## 4. PHP App `data_pasar_modal` (htdocs)

**Lokasi:** `C:\xampp\htdocs\data_pasar_modal\`

### Aset yang berguna:

- **SQL Dump:** `database_export/data_pasar_modal.sql` (176 MB) — backup lengkap database
- **Scraper scripts:** `ai_engine/scrape_idx_*.py` — scraper untuk:
  - `scrape_idx_broker_flow.py` — aliran broker
  - `scrape_idx_foreign_flow.py` — aliran asing
  - `scrape_idx_fundamental.py` — data fundamental
  - `scrape_idx_esg_governance.py` / `scrape_idx_esg_governance_full.py` — ESG & tata kelola
- **AI/ML engine:** `ai_engine/engine.py`, `deep_learning_models.py`, `model_monitoring.py`
- **Fetch scripts:** `scripts/fetch_stock_history.py`, `fetch_fundamental_data.py`
- **Dokumentasi:** `faktor_pasar_modal.md`, `DATABASE_ANALYSIS_REPORT.md`, `DATABASE_RECOMMENDATION_ML_DL.md`, `GAP_ANALYSIS_REPORT.md`, `ML_DL_INTEGRATION_REPORT.md`, `TECH_STACK_ANALYSIS.md`
- **PHP pages:** 22 halaman fungsional (screener, trading, portfolio, journal, strategy, dll.)

---

## 5. Python App `pasar_modal` (htdocs)

**Lokasi:** `C:\xampp\htdocs\pasar_modal\`

### Modul yang bisa diport/adaptasi:

| Modul | File | Fungsi | Relevansi |
|-------|------|--------|-----------|
| **Deep Learning** | `models/deep_learning/` | LSTM, Transformer untuk prediksi harga | **TINGGI** |
| **Traditional ML** | `models/traditional/` | RandomForest, XGBoost | **TINGGI** |
| **Features** | `src/features/` | Feature engineering (technical, fundamental, sentiment) | **TINGGI** |
| **Backtest** | `src/backtest/` | Backtesting engine | **SEDANG** |
| **Regime** | `src/regime/` | Market regime detection | **TINGGI** |
| **Risk** | `src/risk/` | Risk manager, VaR | **SEDANG** |
| **Trading** | `src/trading/` | Execution, Kelly criterion, tax calculator, screener, paper trading | **SEDANG** |
| **XAI** | `src/xai/` | SHAP, LIME explainer | **SEDANG** |
| **Journal** | `src/journal/` | Trade journal | **RENDAH** |
| **Monitoring** | `src/monitoring/` | Model monitoring | **SEDANG** |
| **Notebooks** | `notebooks/` | EDA IHSG, feature analysis, model comparison, backtest analysis | **TINGGI** |

### Tests yang bisa diadaptasi:
`test_kelly_criterion`, `test_regime_detector`, `test_red_flags`, `test_geopolitical`, `test_climate`, `test_sector_metrics`, `test_transaction_costs`, `test_tax_calculator`, `test_monte_carlo`, `test_var`, `test_ensemble`, `test_deep_learning`

---

## 6. External HDD (K:)

### Sudah diexport ke Parquet:
`K:\trading_data\raw\` — 27.7 MB (1,457,076 baris, 10 tabel)

### Tidak ada data saham tambahan:
`K:\saham\` — folder berisi file personal (foto, dokumen), bukan data pasar modal

---

## Rekomendasi Aksi

### Prioritas 1 — Export tabel MySQL yang belum diexport (estimasi ~50 MB Parquet):

```bash
python -m scripts.export_mysql_to_parquet --tables chart_patterns saham_historical multi_asset foreign_flow fear_greed_index saham stock_ipo corporate_governance kebijakan_regulasi esg_scores event_eksternal ai_scores stock_personality pattern_analysis indikator_teknikal saham_teknikal
```

### Prioritas 2 — Import SQLite `saham.db` ke Parquet:
- `global_market_data` (15,046 baris) — mungkin lebih lengkap dari MySQL
- `macro_data` (8,776 baris) — mungkin lebih lengkap dari MySQL
- `ohlcv` (23,851 baris) — cek overlap dengan `stock_history`

### Prioritas 3 — Port modul kode dari `pasar_modal`:
- **Regime detection** → `src/trading_system/analysis/regime.py`
- **Kelly criterion** → `src/trading_system/risk/kelly.py`
- **Tax calculator** → `src/trading_system/execution/tax.py`
- **Deep learning models** → `src/trading_system/ai_learning/deep_learning.py`
- **XAI (SHAP/LIME)** → `src/trading_system/ai_learning/explainers.py`
- **Screener** → `src/trading_system/analysis/screener.py`
- **Red flags detection** → `src/trading_system/analysis/red_flags.py`

### Prioritas 4 — Import master data dari `market_master`:
- 107 instrumen dengan ISIN, sector, sub-sector
- 56 issuer dengan nama perusahaan
- 47 listing dengan ticker, exchange, currency, listing date

### Prioritas 5 — Adaptasi scraper IDX:
- `scrape_idx_broker_flow.py` — untuk refresh broker flow harian
- `scrape_idx_foreign_flow.py` — untuk refresh foreign flow harian
- `scrape_idx_fundamental.py` — untuk refresh fundamental quarterly
- `scrape_idx_esg_governance.py` — untuk refresh ESG scores

---

## Estimasi Total Data Setelah Integrasi Penuh

> **Update 2 Agustus 2026:** Phase 6 selesai. 14 tabel unik dari MySQL `data_pasar_modal` dan `idx_complete_data` telah diimport ke SQLite via `scripts/import_mysql_to_sqlite.py`. Akses read-only via `ExtendedStorage` (`data/extended_storage.py`). Total 95 tabel di SQLite (33 core + 14 import MySQL + 48 tambahan). 15 endpoint `/api/extended/*` tersedia untuk query data import.

| Kategori | Estimasi Baris | Estimasi Parquet | Status |
|----------|---------------|-----------------|--------|
| OHLCV (stock_history + saham_historical) | ~1.4M | ~25 MB | ✅ Di SQLite |
| Chart patterns | 43K | ~2 MB | ✅ Di SQLite |
| Multi-asset (forex, crypto, commodity, index, bond) | 3.3K | ~0.5 MB | ✅ Di SQLite |
| Broker flow + foreign flow | 75K | ~5 MB | ✅ Di SQLite |
| Sentiment + fear/greed | 1.4K | ~0.1 MB | ✅ Di SQLite |
| Macro + global market | 10K | ~0.5 MB | ✅ Di SQLite |
| Fundamental + ESG + governance | 1.2K | ~0.1 MB | ✅ Di SQLite |
| Event eksternal + kebijakan regulasi | 300 | ~0.05 MB | ✅ Di SQLite |
| AI scores + stock personality | 60 | ~0.01 MB | ✅ Di SQLite |
| Master data (saham, sektor, IPO) | 720 | ~0.05 MB | ✅ Di SQLite |
| **Total** | **~1.53M** | **~33 MB** |
