# Mapping Parquet/MySQL → SQLite Schema (§13.4 #4)

> Tanggal: 1 Agustus 2026
> Tujuan: Dokumentasi mapping kolom dari sumber data lama (MySQL `data_pasar_modal`, SQLite `saham.db`) ke schema SQLite `global`.

---

## Ringkasan

Sumber data utama:
1. **MySQL `data_pasar_modal`** (58 tabel, ~1.5M baris) — diexport via `data_pasar_modal/database_export/`
2. **SQLite `pasar_modal/data/saham.db`** (22 tabel, ~48K baris) — hasil migrasi parsial
3. **External HDD** `K:\trading_data\raw\` (Parquet files)

Target: SQLite `global` database dengan 18 tabel D1–D31 (schema baru di `storage.py` + Alembic `0002`).

---

## Mapping Per Tabel

### D1: `instrument_master` ← `saham` / `instruments`

| Sumber (MySQL `saham`) | Target (SQLite `instrument_master`) | Catatan |
|------------------------|--------------------------------------|---------|
| `kode` | `ticker` | Rename; tambah `.JK` suffix untuk IDX |
| `nama` | `name` | |
| `sektor` | `sector` | |
| — | `subsector` | Tidak ada di sumber |
| — | `exchange` | Default `IDX` |
| — | `listing_date` | Tidak ada di sumber |
| — | `delisting_date` | NULL |
| `status` / `is_active` | `is_active` | 1=active, 0=delisted |
| `board` | `board` | |
| — | `market_cap` | Tidak ada di sumber |
| — | `free_float` | Tidak ada di sumber |

**Sumber sekunder:** `saham.db::instruments` (21 rows) — punya `ticker`, `name`, `instrument_type`, `exchange`, `sector`, `industry`, `currency`, `board`, `is_active`.

### D2: `fundamental_data` ← `saham_fundamental`

| Sumber (MySQL `saham_fundamental`) | Target (SQLite `fundamental_data`) | Catatan |
|------------------------------------|-------------------------------------|---------|
| `kode` | `ticker` | |
| `periode` | `date` | Format: `YYYY-MM-DD` atau `YYYY-Qn` |
| `eps` | `earnings_per_share` | |
| `book_value_per_share` | `book_value_per_share` | |
| `net_profit` | `net_profit` | |
| `revenue` | `revenue` | |
| `total_equity` | `total_assets` | Asumsi: equity ≈ assets (perlu verifikasi) |
| — | `total_liabilities` | Tidak ada di sumber |
| — | `cash_flow` | Tidak ada di sumber |
| `npm` | — | Net Profit Margin (derived, tidak disimpan) |
| `revenue_growth` | — | Derived |
| `profit_growth` | — | Derived |
| — | `pe_ratio` | Compute: price / EPS |
| — | `pb_ratio` | Compute: price / book_value |
| — | `roe` | Compute: net_profit / total_equity |
| — | `debt_to_equity` | Tidak ada di sumber |
| — | `dividend_yield` | Compute dari dividends table |
| — | `fiscal_year` | Extract dari periode |
| — | `quarter` | Extract dari periode |
| — | `source` | Default `data_pasar_modal` |

### D3: `macro_data` ← `makroekonomi`

| Sumber (MySQL `makroekonomi`) | Target (SQLite `macro_data`) | Catatan |
|-------------------------------|-------------------------------|---------|
| `periode` | `date` | Format: `YYYY-MM-DD` |
| `suku_bunga` | `value` (series_name=`BI_RATE`) | Unpivot: 1 row per series |
| `inflasi` | `value` (series_name=`INFLATION`) | |
| `gdp_growth` | `value` (series_name=`GDP_GROWTH`) | |
| `kurs_usd` | `value` (series_name=`USD_IDR`) | |
| — | `unit` | `%` untuk rate, `IDR` untuk kurs |
| — | `source` | Default `data_pasar_modal` |
| — | `frequency` | `monthly` |

**Sumber sekunder:** `saham.db::macro_data` (8776 rows) — sudah unpivoted dengan `series_id`, `value`, `region`, `category`.

### D4: `foreign_flow` ← `foreign_flow` (MySQL)

| Sumber (MySQL `foreign_flow`) | Target (SQLite `foreign_flow`) | Catatan |
|-------------------------------|-------------------------------|---------|
| `tanggal` | `date` | |
| `beli` | `foreign_buy` | |
| `jual` | `foreign_sell` | |
| `net` | `foreign_net` | |
| — | `domestic_buy` | Tidak ada di sumber |
| — | `domestic_sell` | Tidak ada di sumber |
| — | `domestic_net` | Tidak ada di sumber |
| — | `ticker` | Default `^JKSE` (IHSG aggregate) |
| — | `source` | Default `data_pasar_modal` |

### D5: `broker_flow` ← `broker_flow` (MySQL)

| Sumber (MySQL `broker_flow`) | Target (SQLite `broker_flow`) | Catatan |
|-------------------------------|-------------------------------|---------|
| `tanggal` | `date` | |
| `kode` | `ticker` | |
| `foreign_buy` | `buy_volume` | Perlu verifikasi: volume atau value? |
| `foreign_sell` | `sell_volume` | |
| `foreign_net` | `net_volume` | |
| `domestic_buy` | `buy_value` | Perlu verifikasi |
| `domestic_sell` | `sell_value` | |
| `domestic_net` | `net_value` | |
| — | `broker` | Tidak ada di sumber (aggregate) |
| — | `source` | Default `data_pasar_modal` |

### D6: `policy_events` ← `kebijakan_regulasi`

| Sumber (MySQL `kebijakan_regulasi`) | Target (SQLite `policy_events`) | Catatan |
|--------------------------------------|---------------------------------|---------|
| `tanggal` | `date` | |
| `jenis` / `tipe` | `event_type` | |
| `deskripsi` | `description` | |
| `dampak` | `impact` | |
| — | `source` | Default `data_pasar_modal` |

### D7: `dividends` ← `dividend` (MySQL)

| Sumber (MySQL `dividend`) | Target (SQLite `dividends`) | Catatan |
|---------------------------|----------------------------|---------|
| `kode` | `ticker` | |
| `tanggal_ex` | `ex_date` | |
| `tanggal_record` | `record_date` | |
| `tanggal_payment` | `payment_date` | |
| `jumlah` | `amount` | |
| — | `currency` | Default `IDR` |
| — | `frequency` | Tidak ada di sumber |
| — | `source` | Default `data_pasar_modal` |

### D8: `sector_master` ← `sektor`

| Sumber (MySQL `sektor`) | Target (SQLite `sector_master`) | Catatan |
|--------------------------|-------------------------------|---------|
| `kode` / `id` | `sector_code` | |
| `nama` | `sector_name` | |
| — | `parent_sector` | Tidak ada di sumber |
| — | `description` | Tidak ada di sumber |

### D9: `market_calendar` — Tidak ada di sumber

Tidak ada tabel kalender bursa di `data_pasar_modal`. Perlu dibuat dari scratch menggunakan data IDX holiday calendar.

### D10: `fear_greed` ← `fear_greed_index`

| Sumber (MySQL `fear_greed_index`) | Target (SQLite `fear_greed`) | Catatan |
|------------------------------------|------------------------------|---------|
| `tanggal` | `date` | |
| `value` / `score` | `value` | |
| `classification` | `classification` | |
| — | `source` | Default `data_pasar_modal` |

### D11: `external_events` ← `event_eksternal`

| Sumber (MySQL `event_eksternal`) | Target (SQLite `external_events`) | Catatan |
|----------------------------------|-----------------------------------|---------|
| `tanggal` | `date` | |
| `tipe` / `jenis` | `event_type` | |
| `deskripsi` | `description` | |
| `region` | `region` | |
| `dampak` / `level` | `impact_level` | |
| — | `source` | Default `data_pasar_modal` |

### D12: `esg_scores` ← `esg_scores`

| Sumber (MySQL `esg_scores`) | Target (SQLite `esg_scores`) | Catatan |
|-----------------------------|-------------------------------|---------|
| `kode` | `ticker` | |
| `tanggal` / `periode` | `date` | |
| `environment_score` | `e_score` | |
| `social_score` | `s_score` | |
| `governance_score` | `g_score` | |
| `total_score` | `esg_score` | |
| — | `source` | Default `data_pasar_modal` |

### D13: `corporate_governance` ← `corporate_governance`

| Sumber (MySQL `corporate_governance`) | Target (SQLite `corporate_governance`) | Catatan |
|----------------------------------------|----------------------------------------|---------|
| `kode` | `ticker` | |
| `tanggal` | `date` | |
| `board_size` | `board_size` | |
| `independent_directors` | `independent_directors` | |
| `audit_committee_quality` | `audit_committee_quality` | |
| `ownership_concentration` | `ownership_concentration` | |
| — | `source` | Default `data_pasar_modal` |

### D14: `stock_personality` ← `stock_personality`

| Sumber (MySQL `stock_personality`) | Target (SQLite `stock_personality`) | Catatan |
|-------------------------------------|--------------------------------------|---------|
| `kode` | `ticker` | |
| `personality_label` | `personality_type` | |
| `volatility_regime` | `volatility_profile` | |
| `liquidity_score` | `liquidity_profile` | |
| `beta_vs_ihsg` | `beta` | |
| — | `correlation_to_ihsg` | Tidak ada di sumber |

### D15: `trade_journal` ← `transaksi` / `journal_entries`

| Sumber (saham.db `journal_entries`) | Target (SQLite `trade_journal`) | Catatan |
|--------------------------------------|---------------------------------|---------|
| `entry_id` | `id` | |
| `ticker` | `ticker` | |
| `entry_date` | `entry_date` | |
| `exit_date` | `exit_date` | |
| `entry_price` | `entry_price` | |
| `exit_price` | `exit_price` | |
| `position_size` | `quantity` | |
| `side` | `side` | |
| `pnl` | `pnl` | |
| `pnl_pct` | `return_pct` | |
| `setup_type` | `strategy` | |
| `notes` | `notes` | |
| — | `tags` | Dari `emotional_state` + `plan_followed` |

### D16: `pattern_analysis` ← `pattern_analysis` / `chart_patterns`

| Sumber (MySQL `pattern_analysis`) | Target (SQLite `pattern_analysis`) | Catatan |
|------------------------------------|-------------------------------------|---------|
| `kode` | `ticker` | |
| `tanggal` / `analysis_date` | `date` | |
| `pattern` | `pattern_type` | |
| `confidence_score` | `confidence` | |
| — | `direction` | Dari `bullish_probability` vs `bearish_probability` |
| `reasoning` | `details` | JSON serialize |
| — | `source` | Default `data_pasar_modal` |

### D17: `valuation_cache` ← `valuation_cache`

| Sumber (MySQL `valuation_cache`) | Target (SQLite `valuation_cache`) | Catatan |
|-----------------------------------|-------------------------------|---------|
| `kode` | `ticker` | |
| `tanggal` | `date` | |
| `method` | `method` | |
| `intrinsic_value` | `intrinsic_value` | |
| `market_price` | `market_price` | |
| `upside_pct` | `upside_pct` | |
| `assumptions` | `assumptions` | |
| — | `source` | Default `data_pasar_modal` |

### D18: `technical_indicators` ← `indikator_teknikal` / `saham_teknikal`

| Sumber (MySQL `indikator_teknikal`) | Target (SQLite `technical_indicators`) | Catatan |
|--------------------------------------|----------------------------------------|---------|
| `kode` | `ticker` | |
| `tanggal` | `date` | |
| — | `indicator` | Unpivot: 1 row per indicator |
| `ma20` | `value` (indicator=`MA20`) | |
| `ma50` | `value` (indicator=`MA50`) | |
| `ma200` | `value` (indicator=`MA200`) | |
| `rsi` | `value` (indicator=`RSI`) | |
| `macd` | `value` (indicator=`MACD`) | |
| `stochastic` | `value` (indicator=`STOCH`) | |
| `support` | `value` (indicator=`SUPPORT`) | |
| `resistance` | `value` (indicator=`RESISTANCE`) | |
| — | `timeframe` | Default `1d` |
| — | `source` | Default `data_pasar_modal` |

---

## OHLCV Mapping (existing table)

| Sumber (MySQL `stock_history`) | Target (SQLite `ohlcv`) | Catatan |
|---------------------------------|--------------------------|---------|
| `kode` | `ticker` | Tambah `.JK` suffix |
| `tanggal` | `timestamp` | Format: `YYYY-MM-DD` |
| `open` | `open` | |
| `high` | `high` | |
| `low` | `low` | |
| `close` | `close` | |
| `volume` | `volume` | |
| — | `adjusted_close` | Compute dari corporate_actions |
| — | `asset_class` | Default `equity` |
| — | `exchange` | Default `IDX` |
| — | `timeframe` | Default `1d` |
| — | `source` | `data_pasar_modal` |
| — | `ingested_at` | UTC timestamp |
| — | `data_quality_score` | NULL saat import |

**Sumber sekunder:** `saham.db::ohlcv` (23851 rows) — punya `date`, `ticker`, `open`, `high`, `low`, `close`, `adj_close`, `volume`, `value`, `frequency`, `data_source`.

---

## Transformasi Umum

1. **Suffix `.JK`**: Semua ticker IDX ditambah suffix `.JK` untuk kompatibilitas dengan yfinance
2. **Date format**: Semua tanggal dikonversi ke `YYYY-MM-DD` (SQLite TEXT)
3. **Unpivot**: Tabel wide format (makroekonomi, indikator_teknikal) di-unpivot ke long format
4. **NULL handling**: Kolom yang tidak ada di sumber → NULL di target
5. **Source tracking**: Semua row diberi `source` = `data_pasar_modal` atau `saham.db`
6. **Deduplication**: `INSERT OR REPLACE` berdasarkan PRIMARY KEY

---

## Prioritas Import

| Prioritas | Tabel | Estimasi Rows | Blocking? |
|-----------|-------|---------------|-----------|
| 1 | `stock_history` → `ohlcv` | 1,370,980 | Ya — Factor Engine butuh data |
| 1 | `saham` → `instrument_master` | 359 | Ya — universe definition |
| 1 | `makroekonomi` → `macro_data` | ~3,000 | Ya — Macro Engine |
| 1 | `foreign_flow` → `foreign_flow` | 465 | Ya — Enhanced Regime |
| 1 | `fear_greed_index` → `fear_greed` | 465 | Ya — Sentiment |
| 2 | `saham_fundamental` → `fundamental_data` | ~5,000 | Factor Engine (quality factor) |
| 2 | `dividend` → `dividends` | ~2,000 | adjusted_close computation |
| 2 | `broker_flow` → `broker_flow` | ~10,000 | Manipulation Detector |
| 2 | `corporate_governance` → `corporate_governance` | 208 | ESG factor |
| 2 | `esg_scores` → `esg_scores` | 164 | ESG factor |
| 2 | `stock_personality` → `stock_personality` | 11 | Stock classification |
| 2 | `pattern_analysis` → `pattern_analysis` | 53 | Pattern Engine |
| 2 | `chart_patterns` → `pattern_analysis` | 43,312 | Pattern Engine |
| 3 | `kebijakan_regulasi` → `policy_events` | 179 | No-Trade Engine |
| 3 | `event_eksternal` → `external_events` | 119 | No-Trade Engine |
| 3 | `valuation_cache` → `valuation_cache` | — | Valuation |
| 3 | `sektor` → `sector_master` | 11 | Reference |
| 3 | `indikator_teknikal` → `technical_indicators` | 465 | Pre-computed cache |
