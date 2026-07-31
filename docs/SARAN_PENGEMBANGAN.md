# Saran Pengembangan Sistem Trading — Hasil Analisa Mendalam

> **Tanggal analisa:** 31 Juli 2026
> **Versi aplikasi:** 0.1.0
> **Cakupan:** Seluruh codebase — `src/trading_system/` (18 engine), `frontend/`, `scripts/`, `tests/`, CI/CD, Docker, dokumentasi.

---

## 1. Ringkasan Eksekutif

Sistem ini memiliki **arsitektur berlapis yang baik** (Data → Analysis → Sentiment → Risk → Decision → Execution → Monitoring) dengan pemisahan tanggung jawab yang jelas, audit trail, mode monitoring default (safe-by-default), dan cakupan tes yang layak (150+ unit test). Namun analisa mendalam menemukan:

- **4 bug fungsional nyata** yang memengaruhi kebenaran keputusan trading (lexicon sentimen, dead code CLI, sinyal SELL yang tidak pernah terjadi, kehilangan arah koefisien di AI Learning).
- **Kelemahan metodologi kuantitatif** (look-ahead bias 1 bar di backtest, VaR parametrik tanpa validasi distribusi, R² in-sample tanpa cross-validation).
- **Kelemahan keamanan & skalabilitas API** (perbandingan API key rawan timing attack, WebSocket tanpa auth, rate-limiter bocor memori).
- **Ketergantungan pada satu sumber data** (yfinance) yang delayed dan tidak resmi untuk IDX.

Prioritas disusun dalam 4 tingkat: **P0 (Kritis — bug)**, **P1 (Tinggi — keamanan & kebenaran kuantitatif)**, **P2 (Menengah — arsitektur & data)**, **P3 (Rendah — peningkatan kualitas)**.

---

## 2. Temuan Kritis (P0) — Bug yang Harus Diperbaiki Segera

### 2.1 Kata "rugi" masuk daftar kata POSITIF di lexicon sentimen

`src/trading_system/sentiment/engine.py` (baris 22–30):

```python
POSITIVE_WORDS = {
    "naik", "tinggi", "untung", "rugi", "positif", ...
}
```

- `"rugi"` jelas kata negatif tetapi ada di `POSITIVE_WORDS` (dan juga di `NEGATIVE_WORDS`) — karena Python `set`, berita berisi "rugi" akan dihitung **positif DAN negatif sekaligus**, menetralkan sinyal.
- Duplikasi lain: `"positif"` dan `"beli"` muncul dua kali di `POSITIVE_WORDS`; `"kerugian"` dua kali di `NEGATIVE_WORDS` (tidak berbahaya, tapi indikasi lexicon tidak pernah di-review).
- Kata netral/ambigu seperti `"volume"`, `"transaksi"`, `"target"`, `"konsolidasi"` dianggap positif — bias skor ke atas.

**Saran:** bersihkan lexicon, pindahkan ke file data (JSON/CSV) yang bisa diaudit, tambahkan unit test yang memverifikasi `POSITIVE_WORDS & NEGATIVE_WORDS == set()`. Jangka menengah: ganti dengan model NLP Indonesia (mis. IndoBERT sentiment fine-tuned) atau minimal VADER-style dengan negasi ("tidak untung" saat ini terhitung positif).

### 2.2 Dead code di CLI: `--monte-carlo` dan `--walk-forward` tidak pernah berjalan

`src/trading_system/cli.py` memiliki **dua blok** `elif args.cmd == "backtest"` (baris 157 dan 187). Blok kedua — yang berisi seluruh logika Monte Carlo, Walk-Forward, dan output metrik lengkap — **tidak akan pernah dieksekusi** karena blok pertama selalu menang. Argumen `--monte-carlo`, `--walk-forward`, `--n-simulations`, `--n-splits` yang terdaftar di parser secara efektif diabaikan.

**Saran:** hapus blok pertama (baris 157–158) dan biarkan blok lengkap yang berjalan; tambahkan test CLI (mis. `pytest` + `capsys`) untuk mencegah regresi serupa.

### 2.3 Decision Engine tidak pernah menghasilkan sinyal SELL

`decision/engine.py::decide_action` hanya mengembalikan `BUY | WATCHLIST | HOLD | AVOID`. Sementara:

- `execution/automated.py::process_signal` memiliki cabang `elif action == "SELL" and position:` — **jalur mati** yang tidak pernah tereksekusi.
- Notifikasi Telegram di `decision/engine.py` mengecek `if action in ("BUY", "SELL")` — kondisi SELL juga mati.

Akibatnya **satu-satunya mekanisme exit adalah stop-loss/take-profit/trailing-stop**. Posisi pada saham dengan conviction memburuk (mis. turun dari 75 → 45) tidak akan dijual selama harga belum menyentuh SL.

**Saran:** definisikan aturan exit eksplisit, contoh: `conviction < 40` **dan** ada posisi terbuka → `SELL`; atau tambahkan `EXIT_THRESHOLD` yang dapat dikonfigurasi. Dokumentasikan state machine sinyal (BUY → HOLD → SELL) dan uji dengan test.

### 2.4 AI Learning membuang arah (tanda) koefisien regresi

`ai_learning/engine.py::train_linear_regression` (baris 232):

```python
coefs = np.abs(reg.coef_)
```

Faktor yang **berkorelasi negatif** dengan forward return (mis. sentiment score tinggi justru diikuti return negatif) tetap mendapat **bobot positif besar**. Ini secara sistematis bisa memperkuat faktor yang justru merugikan.

**Saran:**
- Clip koefisien negatif ke 0 (`np.clip(reg.coef_, 0, None)`) atau gunakan regresi dengan constraint non-negatif (`scipy.optimize.nnls` / `LinearRegression(positive=True)`).
- Validasi out-of-sample: `TimeSeriesSplit` cross-validation, bukan `reg.score()` in-sample (R² in-sample selalu optimis).
- Naikkan ambang minimal sampel dari 20 (terlalu kecil untuk 6 fitur; rule of thumb ≥ 10–20 sampel per fitur → minimal 60–120).
- Simpan riwayat performa bobot AI vs bobot default (A/B) sebelum bobot AI otomatis dipakai `get_factor_weights`.

---

## 3. Prioritas Tinggi (P1) — Kebenaran Kuantitatif & Keamanan

### 3.1 Look-ahead bias 1 bar di Backtest Engine

`backtest/engine.py::run`: sinyal dihitung dari `close` bar yang sama dengan harga eksekusi (`price = row["close"]`). Dalam praktik, sinyal MA crossover baru diketahui **setelah** close, sehingga eksekusi realistis adalah **open bar berikutnya**.

**Saran:**
- Eksekusi di `open` bar t+1 (`df["open"].shift(-1)`) atau minimal `close` t+1.
- Bulatkan `shares` ke lot IDX (100 lembar) — saat ini `shares = (capital * 0.99) // fill_price` menghasilkan lembar bebas, tidak konsisten dengan `automated.py` yang sudah membulatkan lot.
- Terapkan tick size IDX (fraksi harga Rp1/2/5/10/25) pada fill price.
- Refactor: `run` dan `run_with_data` adalah ~90% duplikat — satukan menjadi satu loop inti.

### 3.2 Backtest hanya single-asset, tanpa strategi berbasis Decision Engine

Strategi yang tersedia hanya `BuyAndHold` dan `MovingAverageCrossover`. **Tidak ada backtest untuk strategi yang benar-benar dipakai sistem** (multi-factor conviction score). Artinya klaim performa sistem tidak pernah teruji secara historis.

**Saran:** buat `ConvictionStrategy` yang mereplay skor historis dari tabel `scores` (point-in-time) dan menghasilkan sinyal sesuai `decide_action`. Tambahkan backtest portofolio multi-aset dengan alokasi dari Risk Engine. Ini adalah **fitur paling bernilai** untuk memvalidasi keseluruhan sistem.

### 3.3 Ketidakkonsistenan modal (capital)

- `risk/engine.py::analyze` default `capital = 1_000_000_000`.
- `execution/automated.py` membaca `TRADING_CAPITAL` env (default `100_000_000`).
- `cli.py backtest` default `1_000_000_000`.

`DecisionEngine.recommend` memanggil `self.risk.analyze(ticker)` **tanpa** meneruskan capital, sehingga `position_size` di rekomendasi dihitung dengan modal 1 miliar meskipun robot trading beroperasi dengan 100 juta.

**Saran:** satu sumber kebenaran — `TRADING_CAPITAL` dibaca di `config.py` dan di-inject ke semua engine.

### 3.4 Perhitungan Daily Loss Limit tidak akurat

`automated.py::_check_daily_loss_limit` mengestimasi PnL dengan **rata-rata harga semua BUY historis** untuk ticker tersebut (baris 331–335), bukan harga entry posisi yang benar-benar dijual. Estimasi bisa jauh meleset (mis. buy lama di harga rendah menurunkan rata-rata → loss hari ini tampak lebih kecil → circuit breaker tidak trigger).

**Saran:** simpan `realized_pnl` di tabel `orders` saat SELL dieksekusi (data sudah tersedia di `_execute_sell`), lalu jumlahkan langsung dari kolom itu. Juga: circuit breaker hanya berhenti untuk **satu siklus** — flag "halted for today" perlu dipersist (DB/state) agar siklus berikutnya di hari yang sama tetap berhenti.

### 3.5 Keamanan API

`api/app.py`:

- **Timing attack:** `provided != _API_KEY` (baris 54) — gunakan `secrets.compare_digest`.
- **WebSocket tanpa auth:** semua path `/ws/*` di-skip dari pengecekan API key (baris 52) — `/ws/live` mengekspos status seluruh engine ke siapa pun.
- **Rate limiter bocor memori:** `_rate_limit_store` dict per-IP tidak pernah dibersihkan untuk IP idle; tidak bekerja untuk multi-worker (uvicorn `--workers > 1`) karena in-memory.
- **`POST /api/execution/toggle` dan `/api/rebalance/toggle`** mengubah perilaku trading secara runtime — endpoint paling sensitif ini hanya dilindungi API key opsional (default kosong = tanpa auth).
- `sys.path.insert` hack di `app.py` dan `cli.py` — instal paket secara editable (`pip install -e .`) dan hapus hack.

**Saran:** wajibkan `API_KEY` non-kosong di production (fail-fast saat startup jika `ENV=production` dan key kosong), pakai `slowapi`/Redis untuk rate limiting, tambahkan auth token pada handshake WS, dan pertimbangkan role terpisah (read-only vs admin) untuk endpoint toggle/trigger.

### 3.6 Metodologi risiko

`risk/engine.py`:

- VaR parametrik mengasumsikan distribusi normal — return saham IDX ber-ekor tebal (fat tails); VaR 99% akan **underestimate**. Tambahkan **historical VaR** (percentile empiris) sebagai pembanding — datanya sudah ada.
- `slippage` hard-coded dua level (5/20 bps) — buat fungsi kontinu dari rasio order/ADV.
- Risiko dihitung **per ticker**, tidak ada VaR portofolio dengan korelasi antar-posisi (matriks korelasi sudah tersedia di `relationship_matrix` — manfaatkan).
- Monte Carlo (`backtest/metrics.py`) memakai IID bootstrap — mengabaikan autokorelasi & volatility clustering. Gunakan **block bootstrap** (mis. blok 10–20 hari).

---

## 4. Prioritas Menengah (P2) — Arsitektur, Data, dan Ketahanan

### 4.1 Sumber data tunggal (yfinance) = single point of failure

Seluruh sistem (OHLCV, fundamental, macro, global, corporate actions) bergantung pada Yahoo Finance yang: (a) tidak resmi & bisa berubah/blokir sewaktu-waktu, (b) delayed, (c) data fundamental `.JK` sangat terbatas (sudah diakui di `fundamental.py`), (d) foreign flow & broker summary hanya **proxy** dari harga+volume, bukan data riil IDX.

**Saran:**
- Definisikan interface `DataSourceAdapter` formal dan tambahkan minimal satu sumber alternatif/failover (mis. API IDX resmi untuk broker summary & foreign flow, GoAPI/Sectors.app untuk data IDX, atau data vendor berbayar bila serius production).
- `source_config.yaml` yang disebut di komentar `acquisition.py` belum ada — realisasikan sebagai mekanisme mapping ticker→source.
- Fetch saat ini selalu tarik `period=2y` penuh — implementasikan **incremental fetch** (dari timestamp terakhir di DB) untuk mengurangi beban & rate limit.

### 4.2 Data macro/global menjadi basi (stale)

`analysis/macro.py::ensure_data` dan `global_market.py::ensure_data` hanya fetch **jika tabel kosong**. Setelah fetch pertama, data tidak pernah di-refresh — skor macro/global akan dihitung dari data usang tanpa peringatan.

**Saran:** cek umur data (`max(timestamp)`); refresh jika > 1 hari bursa. Tambahkan `data_age_days` ke breakdown skor agar Decision Engine bisa mendiskon faktor basi.

### 4.3 Penyimpanan: performa dan integritas

`data/storage.py`:

- `save_ohlcv` memakai `iterrows()` + INSERT per baris — sangat lambat untuk ribuan baris. Gunakan `executemany` atau `df.to_sql(..., method="multi")`.
- Koneksi SQLite dibuka/ditutup per operasi tanpa `PRAGMA journal_mode=WAL` — dengan API + scheduler + daily runner menulis bersamaan, risiko `database is locked`. Aktifkan WAL + `busy_timeout`.
- **Skema ganda:** `SCHEMA` string di `storage.py` DAN migrasi Alembic — dua sumber kebenaran yang pasti akan drift. Pilih satu (Alembic) dan jadikan `_init_db` hanya untuk test/dev.
- `adjusted_close` disimpan = `close` (komentar: "belum aksi korporasi") padahal `CorporateActionEngine` sudah ada — integrasikan supaya backtest tidak terdistorsi split/dividen.
- Tidak ada index sekunder (mis. `scores(ticker, engine, as_of)` sudah PK, tapi `audit_log(timestamp)`, `orders(created_at)` belum) — tambahkan untuk query log yang membesar.
- File parquet raw zone menumpuk tanpa retensi (`{ticker}_{interval}_{timestamp}.parquet` setiap fetch) — tambahkan kebijakan retensi/cleanup.

### 4.4 Skalabilitas API & WebSocket

- `_build_engines_status()` meng-import 18 modul + query DB, dan dipanggil **per klien WS setiap 5 detik**. Dengan 10 klien = 120 build/menit. Gunakan satu background task yang broadcast ke semua klien (pattern pub/sub), plus cache TTL untuk `GET /api/engines`.
- Endpoint berat (backtest, Monte Carlo, `POST /api/fetch`) berjalan sinkron di request-response — untuk simulasi besar gunakan background task/job queue dengan endpoint status.
- Tidak ada pagination pada endpoint list (orders, audit logs) — akan berat saat data tumbuh.

### 4.5 Duplikasi logika & konsistensi antar engine

- Perhitungan **ATR** ada 3 versi: `risk/engine.py::_atr`, `execution/automated.py::_get_atr`, `analysis/technical.py` — pindahkan ke satu modul `utils/indicators.py`.
- Logika fee BUY/SELL diduplikasi di `execution/engine.py`, `automated.py`, `rebalancer.py`, `backtest/engine.py` — gunakan `ExecutionEngine.compute_fees` di semua tempat.
- `import json` berulang di dalam fungsi (belasan tempat) — pindah ke top-level import.
- `AutomatedExecutionEngine` mengeksekusi order sendiri **tanpa** memakai `ExecutionEngine.simulate_fill` (tidak ada slippage pada harga eksekusi robot) — inkonsisten dengan backtest yang memakai slippage.

### 4.6 Technical & Macro engine — kualitas sinyal

- **RSI scoring terbalik secara konsep** (`technical.py` baris 122): skor naik linier hingga RSI 70 → RSI 70 (overbought, rawan koreksi) justru mendapat skor momentum maksimal. Pertimbangkan kurva berbentuk lonceng (optimal 50–65, penalti > 70).
- RSI memakai SMA bukan Wilder's smoothing — nilai berbeda dari standar platform trading; pengguna akan bingung membandingkan.
- `macro.py::classify_regime` hanya membandingkan US10Y sekarang vs 20 hari lalu — satu tick naik = "tightening". Terlalu sensitif; gunakan threshold perubahan minimal (mis. ±10 bps) dan konfirmasi multi-indikator. Cabang `growth/slowdown` (baris 60–61) praktis tak terjangkau karena kondisi `us10y_now > / < prev` hampir selalu true.
- `REGIME_WEIGHTS` di `ai_learning/engine.py` memiliki kunci `risk_off` yang tidak pernah dihasilkan `classify_regime` (yang menghasilkan `tightening/easing/growth/slowdown/neutral/unknown`) — sinkronkan taksonomi regime.

### 4.7 Sentiment layer — cakupan & ketahanan

- `_get_company_aliases` dan `TWITTER_KEYWORDS` hard-coded hanya 10 ticker — ticker lain hanya dicari dengan kode mentah (mis. "bbni" jarang muncul di judul berita). Pindahkan mapping ke tabel DB/file konfigurasi yang mudah diperluas.
- Emoji set berisi string non-emoji (`"bull"`, `"capitulation"`) yang dicocokkan sebagai substring — `"bull"` juga match "bullish" yang sudah dihitung lexicon → double counting.
- RSS feed URL hard-coded; jika format berubah, gagal senyap (hanya `logger.debug`). Tambahkan health-check sumber ke tabel `source_health` (mekanismenya sudah ada, tinggal dipakai).
- Tidak ada caching/persistence berita ke tabel `news` (tabel sudah dibuat di skema tapi tampaknya tidak diisi) — sentimen dihitung ulang dari RSS setiap kali, dan riwayat sentimen hilang.

---

## 5. Prioritas Rendah (P3) — Kualitas, DX, dan Fitur Lanjutan

### 5.1 Kualitas kode & tooling

- Tambahkan **ruff** (lint + format) dan **mypy** ke CI — pyflakes saat ini `|| true` (baris 32 `ci.yml`) sehingga lint error tidak pernah menggagalkan build. Minimal hilangkan `|| true`.
- Tambahkan `pip-audit`/`dependabot` untuk keamanan dependensi.
- Pisahkan dependensi dev (pytest, playwright) dari runtime di `pyproject.toml` (`[project.optional-dependencies]`) — image Docker production tidak perlu Playwright.
- Sinkronkan angka test di dokumentasi: `docs/STATUS.md` menyebut **154** di atas dan **117** di bawah; README menyebut 117.

### 5.2 Testing

- Tambah test regresi untuk semua bug P0 di atas.
- **Property-based test** (hypothesis) untuk backtest engine (mis. equity tidak pernah negatif, PnL konsisten dengan trade history).
- Test konkurensi storage (dua writer paralel) setelah WAL diaktifkan.
- E2E API test dengan `TestClient` FastAPI (saat ini e2e hanya browser Playwright).
- Coverage gate di CI (mis. `--cov-fail-under=70`).

### 5.3 Observability

- Structured logging sudah ada — tambahkan **correlation id** per request/cycle eksekusi agar audit trail bisa ditelusuri lintas engine.
- Ekspos metrik Prometheus (`/metrics`): latensi engine, jumlah order, hit rate circuit breaker, umur data per sumber.
- Alert bukan hanya Telegram: fallback email/webhook bila Telegram gagal (saat ini semua `except Exception: pass` — kegagalan notifikasi tidak terlihat sama sekali; minimal log warning).

### 5.4 Fitur lanjutan (sudah ada di roadmap STATUS.md, ditambah usulan baru)

| Fitur | Nilai | Catatan |
|-------|-------|---------|
| Backtest strategi conviction multi-factor | **Sangat tinggi** | Memvalidasi inti sistem (lihat §3.2) |
| Portfolio VaR terkorelasi | Tinggi | Data korelasi sudah ada |
| Historical + Cornish-Fisher VaR | Tinggi | Perbaikan fat-tail |
| Walk-forward CV untuk AI Learning | Tinggi | Prasyarat sebelum bobot AI dipercaya |
| Integrasi broker riil (mis. API sekuritas) di balik interface `BrokerAdapter` | Menengah | Saat ini "eksekusi" hanya menulis DB — dokumentasikan jelas bahwa ini simulasi |
| DCF / Z-Score / F-Score | Menengah | Sesuai roadmap |
| Markowitz / risk-parity untuk rebalancer | Menengah | Target weights saat ini statis dari env |
| IndoBERT sentiment | Menengah | Ganti lexicon |
| Block-bootstrap Monte Carlo | Menengah | Lihat §3.6 |
| Mobile responsive & dark/light | Rendah | Sesuai roadmap |

---

## 6. Peta Jalan yang Disarankan

### Sprint 1 (1–2 minggu) — Perbaikan bug & keamanan dasar
1. Perbaiki lexicon sentimen + test anti-overlap (§2.1).
2. Hapus dead code CLI backtest (§2.2).
3. Implementasikan sinyal SELL berbasis conviction (§2.3).
4. Non-negative constraint + TimeSeriesSplit di AI Learning (§2.4).
5. `secrets.compare_digest`, auth WS, wajibkan API key di production (§3.5).
6. Satukan sumber `TRADING_CAPITAL` (§3.3).
7. Perbaiki perhitungan daily loss limit + persist halt state (§3.4).

### Sprint 2 (2–4 minggu) — Kebenaran kuantitatif
1. Eksekusi backtest next-bar-open + lot 100 + tick size (§3.1).
2. `ConvictionStrategy` backtest end-to-end (§3.2).
3. Historical VaR + block bootstrap MC (§3.6).
4. Refresh data macro/global berbasis umur data (§4.2).
5. Integrasi corporate action → `adjusted_close` (§4.3).

### Sprint 3 (1–2 bulan) — Arsitektur & skala
1. Abstraksi `DataSourceAdapter` + sumber data kedua + incremental fetch (§4.1).
2. WAL + executemany + Alembic sebagai satu-satunya sumber skema (§4.3).
3. WS broadcast tunggal + cache engine status + pagination (§4.4).
4. Konsolidasi ATR/fee/slippage ke modul bersama (§4.5).
5. Ruff + mypy + coverage gate di CI (§5.1, §5.2).

### Berkelanjutan
- Observability (correlation id, Prometheus) — §5.3.
- Fitur lanjutan sesuai tabel §5.4.

---

## 7. Catatan Positif (Yang Sudah Baik — Pertahankan)

- **Safe-by-default:** `AUTO_TRADE_ENABLED=false` dengan mode monitoring; circuit breaker daily loss limit.
- **Audit trail** konsisten di hampir semua aksi penting (order, rekomendasi, fetch).
- **Data quality gate** (`DataQualityValidator` dengan tier & action pause/delayed_review) sebelum data masuk DB.
- **Degradasi anggun** untuk fundamental `.JK` yang datanya minim (`weight_multiplier`, redistribusi bobot) — pola yang matang.
- **Warmup period** di strategi backtest untuk mencegah look-ahead pada indikator (meski eksekusi bar masih perlu diperbaiki, §3.1).
- **Rate limiter yfinance** dengan sliding window + threading lock.
- CI multi-versi Python, build frontend, dan build Docker sudah berjalan.
- Dokumentasi status implementasi (`STATUS.md`) dan buku arsitektur di `docs/` — jarang ditemui pada proyek seukuran ini.

---

## 8. Studi Banding dari Internet — Aplikasi Profesional Sejenis

> Hasil riset terhadap platform dengan tujuan serupa (sistem keputusan trading multi-faktor + backtesting + eksekusi otomatis), baik open-source global maupun produk komersial khusus pasar Indonesia. Digunakan sebagai acuan gap analysis dan sumber ide pengembangan.

### 8.1 Platform algo-trading open-source (pembanding arsitektur inti)

| Platform | Lisensi/Bahasa | Kekuatan yang relevan untuk kita | Pelajaran untuk proyek ini |
|----------|----------------|----------------------------------|---------------------------|
| **QuantConnect Lean** | Apache 2.0, C# + Python API | Kode yang sama untuk backtest dan live trading; multi-aset; integrasi broker (IBKR, OANDA, dll.); data marketplace | **Backtest-live parity** — strategi yang di-backtest harus persis strategi yang dieksekusi robot. Saat ini backtest kita (MA crossover) ≠ strategi live (conviction multi-factor), lihat §3.2 |
| **NautilusTrader** | Python + Rust core | Event-driven dengan simulasi fill akurat (order book, latency), async/await | Model eksekusi realistis: fill di bar berikutnya, partial fill, order lifecycle (NEW→FILLED→CANCELLED) — kita langsung tulis `status='FILLED'` ke DB |
| **Freqtrade** | GPLv3, Python | **Dry-run mode** yang mencerminkan eksekusi live 1:1; kontrol penuh via Telegram bot (start/stop/status/forcesell); **hyperopt** untuk optimasi parameter; FreqAI untuk integrasi ML dengan walk-forward retraining | Mode monitoring kita hanya log pasif — Freqtrade menjadikan paper trading *stateful* (posisi virtual, PnL virtual). Telegram kita satu arah (notifikasi saja), bisa ditingkatkan jadi dua arah (perintah) |
| **Backtrader / backtesting.py** | Python | API strategi yang bersih, analyzer terpisah dari engine | Pisahkan *strategy*, *broker simulation*, dan *analyzer* — backtest engine kita mencampur ketiganya dalam satu loop |
| **vectorbt** | Python | Backtest tervektorisasi sangat cepat untuk hyperparameter sweep | Berguna jika ingin grid-search parameter (mis. threshold conviction, periode MA) — loop `iterrows` kita akan terlalu lambat untuk itu |

**Fitur yang umum di semua platform matang tapi belum ada di sistem kita:**

- **Order lifecycle & tipe order** — limit, stop-limit, GTC/day; kita hanya market-order instan.
- **Paper trading stateful** yang berjalan paralel dengan mode live sebagai validasi terus-menerus.
- **Hyperparameter optimization** (hyperopt/optuna) dengan walk-forward — threshold BUY≥70/WATCHLIST≥55 kita saat ini angka tetap tanpa justifikasi empiris.
- **Strategy versioning** — setiap perubahan bobot/threshold tercatat dan performanya bisa dibandingkan antar versi.
- **Data yang survivorship-bias-free** — universe ticker kita manual; saham delisting tidak tertangani.

### 8.2 Produk komersial pasar Indonesia (pembanding fitur & data)

| Produk | Fitur unggulan yang relevan | Gap di sistem kita |
|--------|------------------------------|--------------------|
| **Stockbit** | Screener 100+ rasio fundamental + teknikal; **Guru Screener** (preset Buffett, Lynch, Piotroski, Greenblatt Magic Formula); PE Standard Deviation Band; perbandingan visual antar emiten; komunitas | Tidak ada fitur **screener** sama sekali — sistem kita hanya menganalisis ticker yang diminta satu per satu. Screener multi-kriteria di atas tabel `scores` adalah quick-win (datanya sudah ada) |
| **RTI Business** | Data real-time IDX, laporan keuangan lengkap, broker summary riil | Foreign flow & broker summary kita hanya **proxy harga+volume** — bukan data riil |
| **IDX Stock Screener (idx.co.id)** | Data fundamental resmi BEI, gratis | Sumber fundamental resmi yang bisa melengkapi yfinance yang datanya `.JK` sangat minim |
| **TradingView** | Charting 100+ indikator, alert berbasis kondisi custom | Alert kita hanya BUY/SELL/risk — tidak ada alert kondisi custom (mis. "RSI < 30 dan volume spike") |
| **Ajaib / broker apps** | Eksekusi riil, kalender emiten (RUPS, dividen, IPO) | Kalender corporate action forward-looking belum ada (kita hanya deteksi historis dari yfinance) |

### 8.3 Sumber data IDX profesional (solusi konkret untuk §4.1)

Riset menemukan penyedia API data IDX yang langsung menjawab kelemahan proxy kita:

- **Sectors.app API** (`api.sectors.app`) — menyediakan persis data yang saat ini kita proksi-kan:
  - `GET /v2/foreign-flow/{symbol}/` — **net foreign inflow harian riil** (IDR) hingga 90 hari → pengganti langsung proxy di `sentiment/foreign_flow.py`.
  - `GET /v2/broker-summary/{symbol}/` — buy/sell/net per broker per hari, dengan klasifikasi **cohort (retail/institutional)** dan **origin (foreign/domestic)** → pengganti langsung `sentiment/broker_summary.py` untuk deteksi smart money yang sebenarnya.
  - Company screener SQL-like, laporan keuangan kuartalan, news & filings, suspensi saham (relevan dengan kata `suspensi` di lexicon kita).
- **GoAPI.io** — alternatif API data saham IDX real-time berbayar lokal.
- **IDX resmi (idx.co.id)** — data fundamental dan ringkasan perdagangan resmi (perlu scraping/unduhan terstruktur).

**Saran implementasi:** jadikan ini sumber kedua di balik interface `DataSourceAdapter` (§4.1) dengan pola *fallback*: Sectors/GoAPI → yfinance → proxy internal. Simpan `source` per record (kolomnya sudah ada di skema) agar kualitas tiap sumber terukur di `source_health`.

### 8.4 Rekomendasi fitur baru hasil studi banding (diurutkan berdasarkan nilai/usaha)

| # | Fitur | Inspirasi | Nilai | Usaha | Catatan |
|---|-------|-----------|-------|-------|---------|
| 1 | **Screener multi-kriteria** di atas tabel `scores` + endpoint `GET /api/screener` | Stockbit, IDX Screener | Tinggi | Rendah | Data skor semua engine sudah tersimpan; tinggal query + UI tabel |
| 2 | **Foreign flow & broker summary riil** via Sectors.app | RTI, Sectors | Tinggi | Rendah–Sedang | Mengganti dua proxy terlemah dengan data riil; butuh API key berbayar |
| 3 | **Paper trading stateful paralel** (posisi & PnL virtual saat `AUTO_TRADE_ENABLED=false`) | Freqtrade dry-run | Tinggi | Sedang | Validasi strategi berkelanjutan sebelum live; infrastruktur `positions/orders` bisa dipakai ulang dengan flag `is_paper` |
| 4 | **Telegram dua arah** (perintah `/status`, `/positions`, `/stop`, `/forcesell TICKER`) | Freqtrade | Sedang | Rendah | `python-telegram-bot`; kontrol darurat tanpa akses server |
| 5 | **Hyperparameter optimization** threshold & bobot (optuna) dengan walk-forward | Freqtrade hyperopt, FreqAI | Tinggi | Sedang | Prasyarat: backtest conviction strategy (§3.2) selesai dulu |
| 6 | **Preset strategi "guru"** (Magic Formula, Piotroski F-Score sebagai preset screener) | Stockbit Guru Screener | Sedang | Sedang | Sinergis dengan roadmap F-Score/Z-Score yang sudah direncanakan |
| 7 | **Alert kondisi custom** (rule builder: indikator + operator + nilai → notifikasi) | TradingView | Sedang | Sedang | Tabel `alert_rules` + evaluasi di siklus scheduler yang sudah ada |
| 8 | **Kalender corporate action forward-looking** (ex-date dividen, RUPS) | Ajaib, RTI | Sedang | Sedang | Sumber: Sectors.app filings / IDX; melengkapi `corporate/actions.py` |
| 9 | **Order lifecycle & limit order** di simulasi eksekusi | Lean, NautilusTrader | Sedang | Tinggi | Prasyarat menuju integrasi broker riil |
| 10 | **Strategy/weights versioning & leaderboard** | QuantConnect | Sedang | Sedang | Bandingkan performa bobot AI vs default vs regime — melengkapi §2.4 |

### 8.5 Posisi strategis

Dibanding platform di atas, **diferensiasi** sistem ini adalah: fokus IDX end-to-end (NLP bahasa Indonesia, fee/lot/pajak IDX, regime makro lokal) + explainable AI dalam bahasa Indonesia. Tidak ada platform open-source yang menggabungkan itu. Saran arah:

1. **Jangan menulis ulang backtest engine dari nol** untuk fitur lanjutan — pertimbangkan integrasi `vectorbt`/`backtesting.py` sebagai engine riset di samping engine internal untuk eksekusi.
2. **Perkuat keunggulan lokal**: data IDX riil (§8.3), lexicon/NLP Indonesia yang benar (§2.1), kalender emiten — hal-hal yang platform global tidak punya.
3. **Adopsi pola yang sudah terbukti** dari Freqtrade/Lean (dry-run stateful, backtest-live parity, kontrol Telegram) daripada menemukan pola sendiri.

---

*Dokumen ini dihasilkan dari analisa statik menyeluruh terhadap kode sumber per 31 Juli 2026, ditambah riset internet terhadap platform sejenis (QuantConnect Lean, NautilusTrader, Freqtrade, Backtrader, vectorbt, Stockbit, RTI Business, IDX Screener, Sectors.app, GoAPI). Setiap referensi baris merujuk pada kondisi file saat analisa dan dapat bergeser setelah perubahan kode.*
