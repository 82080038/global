# Saran Pengembangan Sistem Trading — Hasil Analisa Mendalam

> **Tanggal analisa:** 31 Juli 2026
> **Versi aplikasi:** 0.1.8
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

### 3.1 Look-ahead bias 1 bar di Backtest Engine ✅ SELESAI (v0.1.4)

`backtest/engine.py::run`: sinyal dihitung dari `close` bar yang sama dengan harga eksekusi (`price = row["close"]`). Dalam praktik, sinyal MA crossover baru diketahui **setelah** close, sehingga eksekusi realistis adalah **open bar berikutnya**.

**Saran:**
- Eksekusi di `open` bar t+1 (`df["open"].shift(-1)`) atau minimal `close` t+1.
- Bulatkan `shares` ke lot IDX (100 lembar) — saat ini `shares = (capital * 0.99) // fill_price` menghasilkan lembar bebas, tidak konsisten dengan `automated.py` yang sudah membulatkan lot.
- Terapkan tick size IDX (fraksi harga Rp1/2/5/10/25) pada fill price.
- Refactor: `run` dan `run_with_data` adalah ~90% duplikat — satukan menjadi satu loop inti.

> **Resolved:** Eksekusi next-bar-open (`df["open"].shift(-1)`) diimplementasikan; share count dibulatkan ke `IDX_LOT_SIZE` (100); fill price dibulatkan ke tick size IDX via `round_to_tick()`; `run` dan `run_with_data` disatukan ke `_run_core`.

### 3.2 Backtest hanya single-asset, tanpa strategi berbasis Decision Engine ✅ SELESAI (v0.1.4)

Strategi yang tersedia hanya `BuyAndHold` dan `MovingAverageCrossover`. **Tidak ada backtest untuk strategi yang benar-benar dipakai sistem** (multi-factor conviction score). Artinya klaim performa sistem tidak pernah teruji secara historis.

**Saran:** buat `ConvictionStrategy` yang mereplay skor historis dari tabel `scores` (point-in-time) dan menghasilkan sinyal sesuai `decide_action`. Tambahkan backtest portofolio multi-aset dengan alokasi dari Risk Engine. Ini adalah **fitur paling bernilai** untuk memvalidasi keseluruhan sistem.

> **Resolved:** `ConvictionStrategy` diimplementasikan di `backtest/strategies.py` (v0.1.4). Strategi mereplay skor historis dari tabel `scores` via `pd.merge_asof` (point-in-time) dan menghasilkan sinyal BUY/SELL sesuai `decide_action`. CLI: `--strategy conviction`. API: `POST /api/backtest` dengan `strategy: "conviction"`.

### 3.3 Ketidakkonsistenan modal (capital) ✅ SELESAI (v0.1.3)

- `risk/engine.py::analyze` default `capital = 1_000_000_000`.
- `execution/automated.py` membaca `TRADING_CAPITAL` env (default `100_000_000`).
- `cli.py backtest` default `1_000_000_000`.

`DecisionEngine.recommend` memanggil `self.risk.analyze(ticker)` **tanpa** meneruskan capital, sehingga `position_size` di rekomendasi dihitung dengan modal 1 miliar meskipun robot trading beroperasi dengan 100 juta.

**Saran:** satu sumber kebenaran — `TRADING_CAPITAL` dibaca di `config.py` dan di-inject ke semua engine.

> **Resolved:** `TRADING_CAPITAL` dan `EXIT_CONVICTION_THRESHOLD` disatukan di `config.py` sebagai satu sumber kebenaran, dipakai konsisten di `risk/engine.py`, `decision/engine.py`, `execution/automated.py`, `cli.py`, `api/app.py`.

### 3.4 Perhitungan Daily Loss Limit tidak akurat ✅ SELESAI (v0.1.3)

`automated.py::_check_daily_loss_limit` mengestimasi PnL dengan **rata-rata harga semua BUY historis** untuk ticker tersebut (baris 331–335), bukan harga entry posisi yang benar-benar dijual. Estimasi bisa jauh meleset (mis. buy lama di harga rendah menurunkan rata-rata → loss hari ini tampak lebih kecil → circuit breaker tidak trigger).

**Saran:** simpan `realized_pnl` di tabel `orders` saat SELL dieksekusi (data sudah tersedia di `_execute_sell`), lalu jumlahkan langsung dari kolom itu. Juga: circuit breaker hanya berhenti untuk **satu siklus** — flag "halted for today" perlu dipersist (DB/state) agar siklus berikutnya di hari yang sama tetap berhenti.

> **Resolved:** `realized_pnl` kini disimpan di tabel `orders` saat SELL; daily loss limit dihitung dari kolom tersebut; flag halt dipersist di `system_state`. Win rate calculation di `portfolio/performance.py` juga diperbaiki di v0.1.8 untuk menggunakan `realized_pnl` dari SELL orders.

### 3.5 Keamanan API ✅ SELESAI (v0.1.3 + v0.1.8)

`api/app.py`:

- **Timing attack:** `provided != _API_KEY` (baris 54) — gunakan `secrets.compare_digest`.
- **WebSocket tanpa auth:** semua path `/ws/*` di-skip dari pengecekan API key (baris 52) — `/ws/live` mengekspos status seluruh engine ke siapa pun.
- **Rate limiter bocor memori:** `_rate_limit_store` dict per-IP tidak pernah dibersihkan untuk IP idle; tidak bekerja untuk multi-worker (uvicorn `--workers > 1`) karena in-memory.
- **`POST /api/execution/toggle` dan `/api/rebalance/toggle`** mengubah perilaku trading secara runtime — endpoint paling sensitif ini hanya dilindungi API key opsional (default kosong = tanpa auth).
- `sys.path.insert` hack di `app.py` dan `cli.py` — instal paket secara editable (`pip install -e .`) dan hapus hack.

**Saran:** wajibkan `API_KEY` non-kosong di production (fail-fast saat startup jika `ENV=production` dan key kosong), pakai `slowapi`/Redis untuk rate limiting, tambahkan auth token pada handshake WS, dan pertimbangkan role terpisah (read-only vs admin) untuk endpoint toggle/trigger.

> **Resolved (v0.1.3):** `secrets.compare_digest` diterapkan; auth token di WebSocket `/ws/live`; `API_KEY` wajib di production (fail-fast); rate limiter membersihkan entri idle; endpoint sensitif selalu wajib API key.
>
> **Resolved (v0.1.8):** Sensitive path matching diperbaiki untuk parameterized paths (prefix matching); read-only GET endpoints dikeluarkan dari `_SENSITIVE_PATHS`; POST body validation untuk `/api/rebalance` dan `/api/execution/run` menggunakan `Body(default_factory=dict)`.

### 3.6 Metodologi risiko (sebagian selesai)

`risk/engine.py`:

- VaR parametrik mengasumsikan distribusi normal — return saham IDX ber-ekor tebal (fat tails); VaR 99% akan **underestimate**. Tambahkan **historical VaR** (percentile empiris) sebagai pembanding — datanya sudah ada.
- `slippage` hard-coded dua level (5/20 bps) — buat fungsi kontinu dari rasio order/ADV.
- Risiko dihitung **per ticker**, tidak ada VaR portofolio dengan korelasi antar-posisi (matriks korelasi sudah tersedia di `relationship_matrix` — manfaatkan).
- Monte Carlo (`backtest/metrics.py`) memakai IID bootstrap — mengabaikan autokorelasi & volatility clustering. Gunakan **block bootstrap** (mis. blok 10–20 hari).

> **Resolved (v0.1.3):** Historical VaR (percentile empiris) ditambahkan sebagai pembanding VaR parametrik di `risk/engine.py`.
>
> **Resolved (v0.1.4):** Block bootstrap Monte Carlo diimplementasikan dengan parameter `block_size` di `monte_carlo_simulation` untuk preserve autokorelasi & volatility clustering.
>
> **Belum selesai:** Slippage kontinu dari rasio order/ADV; VaR portofolio dengan korelasi antar-posisi.

---

## 4. Prioritas Menengah (P2) — Arsitektur, Data, dan Ketahanan

### 4.1 Sumber data tunggal (yfinance) = single point of failure ✅ SELESAI (v0.1.5)

Seluruh sistem (OHLCV, fundamental, macro, global, corporate actions) bergantung pada Yahoo Finance yang: (a) tidak resmi & bisa berubah/blokir sewaktu-waktu, (b) delayed, (c) data fundamental `.JK` sangat terbatas (sudah diakui di `fundamental.py`), (d) foreign flow & broker summary hanya **proxy** dari harga+volume, bukan data riil IDX.

**Saran:**
- Definisikan interface `DataSourceAdapter` formal dan tambahkan minimal satu sumber alternatif/failover (mis. API IDX resmi untuk broker summary & foreign flow, GoAPI/Sectors.app untuk data IDX, atau data vendor berbayar bila serius production).
- `source_config.yaml` yang disebut di komentar `acquisition.py` belum ada — realisasikan sebagai mekanisme mapping ticker→source.
- Fetch saat ini selalu tarik `period=2y` penuh — implementasikan **incremental fetch** (dari timestamp terakhir di DB) untuk mengurangi beban & rate limit.

> **Resolved:** `DataSourceAdapter` interface diimplementasikan dengan `SQLiteAdapter`, `CSVAdapter`, `ArchiveAdapter`; `DataSourceManager` dengan priority fallback + auto last_timestamp lookup; `fetch_incremental()` untuk incremental fetch.

### 4.2 Data macro/global menjadi basi (stale) ✅ SELESAI (v0.1.4)

`analysis/macro.py::ensure_data` dan `global_market.py::ensure_data` hanya fetch **jika tabel kosong**. Setelah fetch pertama, data tidak pernah di-refresh — skor macro/global akan dihitung dari data usang tanpa peringatan.

**Saran:** cek umur data (`max(timestamp)`); refresh jika > 1 hari bursa. Tambahkan `data_age_days` ke breakdown skor agar Decision Engine bisa mendiskon faktor basi.

> **Resolved:** `ensure_data` kini menerima `max_age_days` (default 1); re-fetch jika `max(timestamp)` lebih tua dari threshold. `data_age_days` ditambahkan ke breakdown skor macro & global.

### 4.3 Penyimpanan: performa dan integritas ✅ SELESAI (v0.1.5)

`data/storage.py`:

- `save_ohlcv` memakai `iterrows()` + INSERT per baris — sangat lambat untuk ribuan baris. Gunakan `executemany` atau `df.to_sql(..., method="multi")`.
- Koneksi SQLite dibuka/ditutup per operasi tanpa `PRAGMA journal_mode=WAL` — dengan API + scheduler + daily runner menulis bersamaan, risiko `database is locked`. Aktifkan WAL + `busy_timeout`.
- **Skema ganda:** `SCHEMA` string di `storage.py` DAN migrasi Alembic — dua sumber kebenaran yang pasti akan drift. Pilih satu (Alembic) dan jadikan `_init_db` hanya untuk test/dev.
- `adjusted_close` disimpan = `close` (komentar: "belum aksi korporasi") padahal `CorporateActionEngine` sudah ada — integrasikan supaya backtest tidak terdistorsi split/dividen.
- Tidak ada index sekunder (mis. `scores(ticker, engine, as_of)` sudah PK, tapi `audit_log(timestamp)`, `orders(created_at)` belum) — tambahkan untuk query log yang membesar.
- File parquet raw zone menumpuk tanpa retensi (`{ticker}_{interval}_{timestamp}.parquet` setiap fetch) — tambahkan kebijakan retensi/cleanup.

> **Resolved:** WAL journal mode persistent + `synchronous=NORMAL` + 64MB cache; `executemany_batch()` helper untuk large imports; 18 tabel D1–D31 di Alembic migration; `_migrate_legacy_tables()` untuk schema incompatible; `adjusted_close` integration dengan corporate actions (formula split/dividen diperbaiki, auto-fetch, CLI `update-adjusted-close`); index `orders(created_at)` dan `audit_log(timestamp)` ditambahkan.
>
> **Belum selesai:** Retensi/cleanup Parquet raw zone.

### 4.4 Skalabilitas API & WebSocket ✅ SELESAI (v0.1.7)

- `_build_engines_status()` meng-import 18 modul + query DB, dan dipanggil **per klien WS setiap 5 detik**. Dengan 10 klien = 120 build/menit. Gunakan satu background task yang broadcast ke semua klien (pattern pub/sub), plus cache TTL untuk `GET /api/engines`.
- Endpoint berat (backtest, Monte Carlo, `POST /api/fetch`) berjalan sinkron di request-response — untuk simulasi besar gunakan background task/job queue dengan endpoint status.
- Tidak ada pagination pada endpoint list (orders, audit logs) — akan berat saat data tumbuh.

> **Resolved:** Engine status cache (3s TTL) untuk WS `/ws/live` — tidak recompute setiap 5 detik. Pagination di `/api/tickers`, `/api/data/ohlcv`, `/api/watchlist/all`.
>
> **Belum selesai:** Background task/job queue untuk endpoint berat (backtest, Monte Carlo, fetch).

### 4.5 Duplikasi logika & konsistensi antar engine ✅ SELESAI (v0.1.5)

- Perhitungan **ATR** ada 3 versi: `risk/engine.py::_atr`, `execution/automated.py::_get_atr`, `analysis/technical.py` — pindahkan ke satu modul `utils/indicators.py`.
- Logika fee BUY/SELL diduplikasi di `execution/engine.py`, `automated.py`, `rebalancer.py`, `backtest/engine.py` — gunakan `ExecutionEngine.compute_fees` di semua tempat.
- `import json` berulang di dalam fungsi (belasan tempat) — pindah ke top-level import.
- `AutomatedExecutionEngine` mengeksekusi order sendiri **tanpa** memakai `ExecutionEngine.simulate_fill` (tidak ada slippage pada harga eksekusi robot) — inkonsisten dengan backtest yang memakai slippage.

> **Resolved:** `risk/costs.py` sebagai single source of truth: `compute_atr()`, `get_latest_atr()`, `CostModel` (buy/sell fee, levy, slippage, simulate_fill, check_feasibility). Semua engine kini delegasi ke `costs.py`: `risk/engine.py`, `execution/engine.py`, `execution/automated.py`, `backtest/engine.py`, `analysis/technical.py`.

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

### 5.1 Kualitas kode & tooling ✅ SELESAI (v0.1.7)

- Tambahkan **ruff** (lint + format) dan **mypy** ke CI — pyflakes saat ini `|| true` (baris 32 `ci.yml`) sehingga lint error tidak pernah menggagalkan build. Minimal hilangkan `|| true`.
- Tambahkan `pip-audit`/`dependabot` untuk keamanan dependensi.
- Pisahkan dependensi dev (pytest, playwright) dari runtime di `pyproject.toml` (`[project.optional-dependencies]`) — image Docker production tidak perlu Playwright.
- Sinkronkan angka test di dokumentasi: `docs/STATUS.md` menyebut **154** di atas dan **117** di bawah; README menyebut 117.

> **Resolved:** Ruff (192 errors → 0, 247 auto-fixed) + mypy (non-blocking) + coverage gate 50% (actual 69%) di CI. Angka test disinkronkan: 562 di semua dokumentasi.
>
> **Belum selesai:** `pip-audit`/`dependabot`; pemisahan dependensi dev vs runtime di `pyproject.toml`.

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

### Sprint 1 (1–2 minggu) — Perbaikan bug & keamanan dasar ✅ SELESAI
1. ✅ Perbaiki lexicon sentimen + test anti-overlap (§2.1).
2. ✅ Hapus dead code CLI backtest (§2.2).
3. ✅ Implementasikan sinyal SELL berbasis conviction (§2.3).
4. ✅ Non-negative constraint + TimeSeriesSplit di AI Learning (§2.4).
5. ✅ `secrets.compare_digest`, auth WS, wajibkan API key di production (§3.5).
6. ✅ Satukan sumber `TRADING_CAPITAL` (§3.3).
7. ✅ Perbaiki perhitungan daily loss limit + persist halt state (§3.4).

### Sprint 2 (2–4 minggu) — Kebenaran kuantitatif ✅ SELESAI
1. ✅ Eksekusi backtest next-bar-open + lot 100 + tick size (§3.1).
2. ✅ `ConvictionStrategy` backtest end-to-end (§3.2).
3. ✅ Historical VaR + block bootstrap MC (§3.6).
4. ✅ Refresh data macro/global berbasis umur data (§4.2).
5. ✅ Integrasi corporate action → `adjusted_close` (§4.3) — formula split/dividen diperbaiki, auto-fetch corporate actions, CLI `update-adjusted-close`.

### Sprint 3 (1–2 bulan) — Arsitektur & skala ✅ SELESAI
1. ✅ Abstraksi `DataSourceAdapter` multi-sumber + incremental fetch (§4.1) — `SQLiteAdapter`, `CSVAdapter`, `DataSourceManager` dengan priority fallback.
2. ✅ WAL + executemany + Alembic sebagai satu-satunya sumber skema (§4.3) — WAL persistent, `executemany_batch()`, 18 tabel D1–D31 di Alembic `0002`.
3. ✅ WS broadcast tunggal + cache engine status + pagination (§4.4) — engine status cache (3s TTL), pagination di 3 endpoint.
4. ✅ Konsolidasi ATR/fee/slippage ke modul bersama (§4.5) — `risk/costs.py` sebagai single source of truth.
5. ✅ Ruff + mypy + coverage gate di CI (§5.1, §5.2) — ruff (192→0 errors), mypy non-blocking, coverage gate 50% (actual 69%).

**Yang sudah selesai di Sprint 3:**
- ✅ Export seluruh MySQL `data_pasar_modal` (60+ tabel, 1.5M baris) + SQLite ke Parquet archive di `K:\trading_data\raw` (174 files, ~33 MB).
- ✅ `DATA_ARCHIVE_DIR` config + `ArchiveAdapter` untuk baca/tulis Parquet.
- ✅ Port modul dari `pasar_modal`: `regime.py`, `kelly.py`, `tax.py`, `red_flags.py`, `screener.py`, `idx_scraper.py`.

### Sprint 4 — Adopsi komponen dari repo lain ✅ SELESAI
> Lihat §9.6 untuk detail Fase 1–4, dan §12.4 untuk strategi implementasi.
> Semua komponen A–FF telah diimplementasi (562 unit tests passing).

### Berkelanjutan
- Observability (correlation id, Prometheus) — §5.3.
- Fitur lanjutan sesuai tabel §5.4.
- Sinkronisasi dokumentasi & maintenance.

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

## 9. Aset dari Repository Lokal — Adopsi ke Aplikasi Ini

> **Tanggal analisa:** 1 Agustus 2026
> **Cakupan:** Eksplorasi menyeluruh dari 3 sumber: (1) HDD lokal `C:\xampp\htdocs\` dan `K:\xampp\htdocs\`, (2) HDD eksternal `D:\` dan `L:\`, (3) 94 repository GitHub di `https://github.com/82080038?tab=repositories`. Identifikasi komponen bernilai untuk diadopsi ke `global`, dengan rencana integrasi.
>
> **Drive yang diperiksa:** `C:\` (htdocs), `K:\` (htdocs), `D:\` (hanya game), `L:\` (file personal — tidak ada kode trading). GitHub: 94 repo, 7 di antaranya relevan dengan trading/saham.

### 9.0 Repository yang Ditemukan

| Repository | Lokasi | Bahasa | Status | Deskripsi singkat |
|-----------|--------|--------|--------|-------------------|
| **pasar_modal** | `C:\xampp\htdocs\pasar_modal\` | Python (FastAPI + Streamlit) | Blueprint + sebagian implementasi | Sistem proyeksi saham IHSG dengan ML/DL, XAI, regime detection, sector metrics, red flags |
| **swing** | `K:\xampp\htdocs\swing\` | Python | Aplikasi lengkap, banyak script | Swing trading system dengan paper trading stateful, screener, manipulation detector, portfolio optimizer, ARIMA/XGBoost ensemble |
| **ML** | `K:\xampp\htdocs\ML\` | Python | Framework + stubs | ML trading framework dengan labeling, purged CV, walk-forward validation, MLOps (model registry, monitor) |
| **data_pasar_modal** | `C:\xampp\htdocs\data_pasar_modal\` | PHP + Python | Aplikasi web + scraper | Sistem data pasar modal dengan scraper IDX (foreign flow, broker flow, fundamental dari PDF, ESG/governance) |
| **trading-otomatis-indonesia** | `https://github.com/82080038/trading-otomatis-indonesia` | PHP + Python (TensorFlow) | Aplikasi lengkap, 44+ modul Python | AI trading system dengan LSTM/GRU/Transformer, ensemble ML, order book analyzer, pattern engine, pre/post market analyzer, trading bot, time-lapse mode |
| **AI_Trading** | `https://github.com/82080038/AI_Trading` | PHP + Python | XAMPP-based, lengkap | AI Trading Assistant dengan symbol discovery (ID/US/Crypto), 20+ indikator teknikal, ML predictions, portfolio tracking |
| **belajar_saham** | `https://github.com/82080038/belajar_saham` | Python | Edukasi + simulasi | Trading expectancy calculator, backtest SMA 50, simulasi AI saham, submodule `saham` (pipeline AI trading) |
| **worldmonitor** | `https://github.com/82080038/worldmonitor` | TypeScript (Next.js + Tauri) | Fork, aplikasi lengkap | Real-time global intelligence dashboard: 500+ news feeds, AI synthesis, Country Instability Index, finance radar (29 bursa, komoditas, crypto), 7-signal market composite |
| **bandarmologi** | `https://github.com/82080038/bandarmologi` | — | Empty repo (README only) | Konsep bandarmologi (belum ada kode) |
| **TIP** | `C:\xampp\htdocs\TIP\` | Python + PHP (FastAPI + PostgreSQL/TimescaleDB) | **Lengkap, 300 tests passing, 8 fase** | Trading Intelligence Platform: factor engine (7 faktor), alpha composer, no-trade engine (9 gates), cross-asset engine, lead-lag analyzer, global+Indonesia regime, alpha validation lab, risk engine (vol-targeted), data quality engine, rate limiter dengan circuit breaker |

### 9.1 Komponen Prioritas Tinggi — Adopsi Langsung

#### A. Scraper IDX Foreign Flow (real data, bukan proxy)

- **Sumber:** `C:\xampp\htdocs\data_pasar_modal\ai_engine\scrape_idx_foreign_flow.py`
- **Mengapa perlu diambil:** Saat ini `sentiment/foreign_flow.py` di aplikasi ini hanya **proxy** dari harga+volume (diakui di §4.1 dan §8.2). Scraper ini mengambil **data riil** foreign buy/sell per saham dari endpoint `idx.co.id/primary/TradingSummary/getStockSummary` — gratis, resmi, dan tersedia dari Jan 2020.
- **Cara adopsi:** Convert dari MySQL/subprocess → SQLite/Python murni. Buat sebagai implementasi `DataSourceAdapter` (§4.1). Ganti `cloudscraper` dengan `httpx` (sudah di `pyproject.toml`). Simpan ke tabel `foreign_flow` di SQLite (tambahkan via Alembic migration). Rate limiting 0.3s/request sudah sesuai.
- **Estimasi usaha:** Rendah–Sedang (convert DB layer + integrasi ke pipeline)
- **Mengatasi:** §4.1 (sumber data tunggal), §8.2 (foreign flow proxy), §8.3 (sumber data IDX)

#### B. Scraper IDX Broker Summary (real data, bukan proxy)

- **Sumber:** `C:\xampp\htdocs\data_pasar_modal\ai_engine\scrape_idx_broker_flow.py`
- **Mengapa perlu diambil:** `sentiment/broker_summary.py` saat ini juga proxy. Scraper ini mengambil **broker summary riil** dari `idx.co.id/primary/TradingSummary/getBrokerSummary` — aggregate buy/sell per broker per hari.
- **Cara adopsi:** Sama seperti A — convert MySQL → SQLite, integrasi sebagai `DataSourceAdapter`. Data per-broker bisa dikelompokkan (retail vs institutional) untuk deteksi smart money yang sebenarnya.
- **Estimasi usaha:** Rendah–Sedang
- **Mengatasi:** §4.1, §8.2 (broker summary proxy), §8.3

#### C. Purged Time Series Split (anti data-leakage CV)

- **Sumber:** `K:\xampp\htdocs\ML\validation\purged_time_series_split.py` (82 baris)
- **Mengapa perlu diambil:** AI Learning (`ai_learning/engine.py`) saat ini memakai `reg.score()` in-sample (§2.4) — tidak ada cross-validation. Modul ini mengimplementasikan **Purged K-Fold** dengan `purge_gap` (default 10 hari) dan `embargo_period` (default 20 hari) untuk mencegah data leakage pada time series — metode Lopez de Prado.
- **Cara adopsi:** **Raw copy** ke `src/trading_system/ai_learning/purged_cv.py`. Tidak ada dependency eksternal selain numpy/pandas. Gunakan di `train_linear_regression` untuk menggantikan `reg.score()`:
  ```python
  splitter = PurgedTimeSeriesSplit(n_splits=5, purge_gap=10, embargo_period=20)
  for train_idx, test_idx in splitter.split(df):
      model.fit(X.iloc[train_idx], y.iloc[train_idx])
      score = model.score(X.iloc[test_idx], y.iloc[test_idx])
  ```
- **Estimasi usaha:** Rendah (raw copy + integrasi ~30 menit)
- **Mengatasi:** §2.4 (AI Learning validasi), §5.4 (walk-forward CV)

#### D. Walk-Forward Validator

- **Sumber:** `K:\xampp\htdocs\ML\validation\walk_forward_validator.py` (124 baris)
- **Mengapa perlu diambil:** Backtest engine saat ini tidak punya walk-forward analysis (§3.2, §5.4). Modul ini mengimplementasikan walk-forward dengan training window (default 252 hari = 1 tahun), step size (default 63 hari = 1 kuartal), embargo, dan per-split accuracy + Sharpe metric.
- **Cara adopsi:** **Raw copy** ke `src/trading_system/backtest/walk_forward.py`. Integrasi dengan `ConvictionStrategy` (§3.2) saat sudah dibuat. Dependency: `PurgedTimeSeriesSplit` (komponen C di atas).
- **Estimasi usaha:** Rendah (raw copy + integrasi dengan backtest engine)
- **Mengatasi:** §3.2 (backtest conviction strategy), §5.4 (walk-forward CV)

#### E. Stateful Paper Trading Engine

- **Sumber:** `K:\xampp\htdocs\swing\modules\paper_trading.py` (362 baris)
- **Mengapa perlu diambil:** Paper trading di aplikasi ini (`paper_trading/engine.py`, 58 baris) hanya simulasi **single-shot per ticker** — tidak menyimpan posisi, tidak track PnL, tidak ada account balance. Modul swing ini mengimplementasikan **paper trading stateful penuh**: account balance (cash, buying power, margin), posisi dengan SL/TP, eksekusi BUY/SELL dengan fee, realized PnL per trade, portfolio summary dengan unrealized PnL.
- **Cara adopsi:** Convert dari swing's SQLite schema (`account_balance`, `positions`, `trade_history`) ke `global`'s storage. Tambahkan flag `is_paper` ke tabel `orders` dan `positions` (jika belum ada) via Alembic. Buat tabel `paper_account_balance`. Gunakan `ExecutionEngine.compute_fees` yang sudah ada (§4.5) sebagai ganti `risk_manager.calculate_total_fees`. Integrasi dengan `DecisionEngine.recommend` sebagai input.
- **Estimasi usaha:** Sedang (adaptasi schema + integrasi dengan engine yang sudah ada)
- **Mengatasi:** §8.4 #3 (paper trading stateful paralel), §8.1 (backtest-live parity)

#### F. Enhanced Market Regime Detector

- **Sumber:** `C:\xampp\htdocs\pasar_modal\src\regime\detector.py` (301 baris)
- **Mengapa perlu diambil:** Regime detection di aplikasi ini (`analysis/regime.py`, 49 baris) hanya 4 fungsi sederhana dengan 4 regime (trending/neutral/volatile/shock). Versi `pasar_modal` punya **6 regime** (BULL/BEAR/SIDEWAYS/HIGH_VOLATILITY/LOW_VOLATILITY/CRISIS), **multi-indikator** (IHSG vs SMA200, VIX, yield curve, DXY, foreign flow, ATR), **confidence score** per deteksi, dan fungsi `apply_regime_filter` untuk filter backtest/trading berdasarkan regime.
- **Cara adopsi:** **Raw copy** ke `src/trading_system/analysis/regime.py` (replace existing). Adaptasi: `global` sudah punya `macro.py` yang menyediakan data VIX, US10Y, DXY — gunakan sebagai input. Sinkronkan `RegimeType` dengan `REGIME_WEIGHTS` di `ai_learning/engine.py` (§4.6). Tambahkan `regime_to_multiplier` mapping untuk 6 regime baru.
- **Estimasi usaha:** Sedang (replace + integrasi dengan macro engine + AI Learning)
- **Mengatasi:** §4.6 (regime detection terlalu sensitif), §4.6 (REGIME_WEIGHTS mismatch), §3.6 (regime-aware risk)

#### G. Scraper IDX Fundamental dari Annual Report PDF

- **Sumber:** `C:\xampp\htdocs\data_pasar_modal\ai_engine\scrape_idx_fundamental.py` (475 baris)
- **Mengapa perlu diambil:** Data fundamental `.JK` dari yfinance sangat terbatas (§4.1, diakui di `fundamental.py`). Scraper ini mengunduh **laporan tahunan PDF dari idx.co.id**, mengekstrak **5-year financial summary** (revenue, net income, total assets, equity, dll) menggunakan `pdfplumber`. Satuh PDF mencakup 5 tahun data, jadi download report 2024/2019/2014/2009 → coverage 2004–2024 (~20 tahun).
- **Cara adopsi:** Convert MySQL → SQLite. Tambah `pdfplumber` ke `pyproject.toml` (opsional — hanya untuk fetch fundamental mendalam). Buat sebagai method di `DataSourceAdapter` atau modul terpisah `data/idx_fundamental_scraper.py`. Sebagai fallback bila yfinance fundamental minim, ini sumber paling lengkap untuk IDX.
- **Estimasi usaha:** Sedang (PDF parsing + convert DB + integrasi)
- **Mengatasi:** §4.1 (fundamental .JK terbatas), §8.2 (IDX Screener fundamental resmi)

### 9.2 Komponen Prioritas Menengah — Adopsi dengan Adaptasi

#### H. Performance Attribution Analysis

- **Sumber:** `K:\xampp\htdocs\swing\modules\performance_attribution.py` (375 baris)
- **Mengapa perlu diambil:** Aplikasi ini punya `portfolio/performance.py` tapi tidak ada **performance attribution** — dekomposisi return berdasarkan: (1) stock selection (top/bottom performers per ticker), (2) sector allocation (PnL per sektor), (3) timing (entry timing: pagi/siang, holding period: winning vs losing days), (4) risk management (efektivitas SL/TP: berapa loss dicegah, berapa profit direalisasi).
- **Cara adopsi:** Convert dari swing's `trade_history` table ke `global`'s `orders` table. Gunakan `analysis/relationship.py` untuk sector mapping (atau buat mapping sektor JASICA). Output sebagai endpoint API `GET /api/attribution` dan tampilkan di dashboard.
- **Estimasi usaha:** Sedang
- **Mengatasi:** §5.4 (strategy versioning & leaderboard), fitur baru tidak ada di roadmap

#### I. Correlation-Based Position Sizing

- **Sumber:** `K:\xampp\htdocs\swing\modules\correlation_manager.py` (341 baris)
- **Mengapa perlu diambil:** Aplikasi ini sudah punya `analysis/relationship.py` (matriks korelasi) tapi **tidak dipakai untuk position sizing** (§3.6). Modul swing ini: (1) hitung matriks korelasi return antar saham, (2) temukan pasangan highly correlated (threshold 0.7), (3) reduksi position size untuk saham yang berkorelasi tinggi (max 20% allocation untuk correlated group).
- **Cara adopsi:** Integrasikan ke `risk/engine.py::analyze` — setelah hitung position size individual, terapkan correlation penalty. Gunakan data dari `analysis/relationship.py` yang sudah ada. Tambah parameter `correlation_threshold` dan `max_correlated_allocation` ke `config.py`.
- **Estimasi usaha:** Sedang
- **Mengatasi:** §3.6 (portfolio VaR dengan korelasi), §4.5 (konsolidasi ATR/indikator)

#### J. Sector-Specific Metrics (JASICA 11 Sektor)

- **Sumber:** `C:\xampp\htdocs\pasar_modal\src\features\sector_metrics.py` (406 baris)
- **Mengapa perlu diambil:** Fundamental analysis saat ini generic (PER, PBV, ROE, DER untuk semua saham). Modul ini definisikan **metrics spesifik per sektor** JASICA:
  - **Banking:** NPL ratio, CAR, NIM, LDR, CASA ratio
  - **Mining:** Cash cost, AISC, strip ratio, reserve life
  - **Property:** Unsold inventory, land bank, recurring revenue, marketing sales
  - **Consumer:** Same-store sales growth, inventory turnover, gross margin, market share
  - **Telecom:** ARPU, churn rate, capex intensity, data center capacity
  - **Energy, Plantation, dll.**
- **Cara adopsi:** **Raw copy** ke `src/trading_system/analysis/sector_metrics.py`. Buat mapping ticker→sektor (swing punya `SECTOR_MAPPING` di `portfolio_optimizer.py` yang bisa dijadikan dasar). Integrasi ke `fundamental.py` — saat ticker masuk sektor tertentu, hitung metrics spesifik dan tambahkan ke skor fundamental.
- **Estimasi usaha:** Sedang (butuh data input dari scraper fundamental G)
- **Mengatasi:** §5.4 (DCF/Z-Score/F-Score), fitur baru untuk kedalaman fundamental

#### K. Advanced Technical Indicators (Ichimoku + Parabolic SAR)

- **Sumber:** `C:\xampp\htdocs\pasar_modal\src\features\advanced_technical.py` (513 baris)
- **Mengapa perlu diambil:** Technical engine saat ini hanya punya MA, RSI, MACD, Bollinger, ADX. Modul ini menambahkan: (1) **Ichimoku Cloud** (Tenkan-sen, Kijun-sen, Senkou Span A/B, Chikou Span) — sistem trading lengkap dari Jepang, (2) **Parabolic SAR** (Stop and Reverse) — trend following + trailing stop, (3) indikator lain (Williams %R, CCI, dll. di file yang sama).
- **Cara adopsi:** **Raw copy** ke `src/trading_system/analysis/advanced_technical.py` atau tambahkan ke `utils/indicators.py` yang sudah direncanakan (§4.5). Integrasi ke `technical.py` sebagai indikator tambahan untuk scoring.
- **Estimasi usaha:** Rendah (raw copy, fungsi murni pandas/numpy)
- **Mengatasi:** §4.5 (konsolidasi indikator), §4.6 (kualitas sinyal teknikal)

#### L. Model Registry + Model Monitor (MLOps)

- **Sumber:**
  - `K:\xampp\htdocs\ML\mlops\model_registry.py` (187 baris) — versioning dengan MLflow atau file-based fallback
  - `K:\xampp\htdocs\ML\mlops\model_monitor.py` (181 baris) — prediction drift, feature drift, performance decay
- **Mengapa perlu diambil:** AI Learning saat ini melatih model tapi tidak ada **versioning** (§5.4) dan tidak ada **monitoring drift**. Setiap perubahan bobot tidak tercatat — tidak bisa membandingkan performa bobot AI vs default (§2.4). Model Registry: simpan model + metadata (metrics, features, training date) per versi. Model Monitor: deteksi prediction drift (distribusi prediksi berubah), feature drift (distribusi fitur berubah), performance decay (Sharpe turun >20%).
- **Cara adopsi:** Raw copy kedua file ke `src/trading_system/ai_learning/`. Model Registry: gunakan file-based fallback (MLflow opsional). Integrasikan ke `train_linear_regression` — setiap training, register model baru. Model Monitor: jalankan setiap cycle scheduler, log warning bila drift terdeteksi.
- **Estimasi usaha:** Sedang
- **Mengatasi:** §2.4 (simpan riwayat performa bobot AI vs default), §5.4 (strategy versioning & leaderboard)

#### M. Market Manipulation Detector

- **Sumber:** `K:\xampp\htdocs\swing\modules\advanced_manipulation_detector.py` (663 baris)
- **Mengapa perlu diambil:** Tidak ada deteksi manipulasi pasar di aplikasi ini. Modul swing ini deteksi: (1) **Intraday anomaly** — volume >3x rata-rata + range >5% = pump alert; volume >2x + return <-3% = dump alert, (2) **Spoofing patterns** — orde besar yang dibatalkan, (3) **ML-based detection** — RandomForest + XGBoost ensemble untuk klasifikasi manipulasi.
- **Cara adopsi:** Adaptasi ke `src/trading_system/analysis/manipulation_detector.py`. Gunakan data intraday dari yfinance (interval 15m, period 5d). Tambahkan sebagai engine baru di pipeline analisis. Output: flag `manipulation_risk` di Decision Engine untuk mendiskon conviction.
- **Estimasi usaha:** Sedang–Tinggi (ML training + integrasi)
- **Mengatasi:** Fitur baru, melengkapi sentiment layer dengan deteksi anomali

#### N. Alpha-Adjusted Labeling

- **Sumber:** `K:\xampp\htdocs\ML\labeling\label_creator.py` (134 baris) + `K:\xampp\htdocs\ML\labeling\alpha_calculator.py` (2,3 KB)
- **Mengapa perlu diambil:** AI Learning saat ini memakai forward return mentah sebagai target. Labeling ini menyesuaikan return dengan **alpha** (excess return vs IHSG) — saham naik 3% saat IHSG naik 5% sebenarnya underperform (bukan BUY). Juga: multi-horizon labels (1/5/22 hari), liquidity filter (bottom 20% volume = NO_TRADE).
- **Cara adopsi:** Raw copy ke `src/trading_system/ai_learning/labeling.py`. Gunakan IHSG data dari `data/storage.py`. Integrasi ke `train_linear_regression` sebagai pre-processing label.
- **Estimasi usaha:** Rendah
- **Mengatasi:** §2.4 (AI Learning kualitas), §5.4 (fitur lanjutan)

#### S. Deep Learning Models (LSTM + GRU + Transformer Ensemble)

- **Sumber:** `https://github.com/82080038/trading-otomatis-indonesia/blob/main/python/ai_components/advanced_deep_learning_models.py`
- **Mengapa perlu diambil:** AI Learning saat ini hanya memakai `LinearRegression` (§2.4) — tidak ada deep learning. Modul ini mengimplementasikan: (1) **LSTM** multi-layer dengan dropout untuk sequence prediction, (2) **GRU** (lebih ringan dari LSTM, cocok untuk dataset kecil), (3) **Transformer** dengan MultiHeadAttention untuk time series, (4) **Ensemble model** yang menggabungkan LSTM + GRU + Transformer dalam satu model multi-input. Semua dengan `prepare_data()` (MinMaxScaler, sequence windowing) dan training callbacks (EarlyStopping, ReduceLROnPlateau).
- **Cara adopsi:** Convert ke `src/trading_system/ai_learning/deep_learning.py`. Tambah `tensorflow` ke `pyproject.toml` (opsional — gunakan flag `DL_AVAILABLE` seperti `HAS_ML` di swing). Gunakan sebagai model alternatif di `train_linear_regression` — jika TF available, latih DL model sebagai comparator. Integrasi dengan Purged CV (komponen C) untuk validasi.
- **Estimasi usaha:** Sedang (convert + integrasi + dependency management)
- **Mengatasi:** §2.4 (AI Learning hanya LinearRegression), §5.4 (DL models)

#### T. Advanced Ensemble System (Voting + Stacking + Weighted)

- **Sumber:** `https://github.com/82080038/trading-otomatis-indonesia/blob/main/python/ai_components/advanced_ensemble_system.py`
- **Mengapa perlu diambil:** AI Learning tidak punya ensemble methods. Modul ini mengimplementasikan 3 strategi ensemble: (1) **VotingClassifier** (soft voting dengan RF + LR + SVM + MLP), (2) **StackingClassifier** (meta-learner LogisticRegression dengan 5-fold CV), (3) **Weighted ensemble** (custom weights berdasarkan performance score). Termasuk `train_ensemble_models()` dengan cross-validation per model dan `predict_ensemble()` yang menggabungkan semua.
- **Cara adopsi:** Convert ke `src/trading_system/ai_learning/ensemble.py`. Gunakan sebagai upgrade dari `train_linear_regression` — latih ensemble sebagai model utama, LinearRegression sebagai baseline. Integrasi dengan Model Registry (komponen L) untuk versioning.
- **Estimasi usaha:** Sedang
- **Mengatasi:** §2.4 (AI Learning kualitas), §5.4 (ensemble methods)

#### U. Order Book Analyzer (Gap + Support/Resistance)

- **Sumber:** `https://github.com/82080038/trading-otomatis-indonesia/blob/main/python/ai_components/order_book_analyzer.py`
- **Mengapa perlu diambil:** Tidak ada analisis order book / gap di aplikasi ini. Modul ini: (1) **Price gap detection** — identifikasi gap >2% antar candle, (2) **Volume gap detection** — identifikasi perubahan volume >50%, (3) **Support/Resistance identification** — level yang diuji minimal 3x dengan tolerance 1%, (4) **Gap strength scoring** — ukur kekuatan gap berdasarkan rasio. Konsep: gap dalam order book menciptakan pola yang memengaruhi pergerakan harga.
- **Cara adopsi:** **Raw copy** ke `src/trading_system/analysis/order_book.py`. Murni pandas/numpy, tidak ada dependency eksternal. Integrasi ke `technical.py` sebagai sinyal tambahan (gap_alert, support_resistance_levels).
- **Estimasi usaha:** Rendah (raw copy, fungsi murni)
- **Mengatasi:** §4.5 (indikator tambahan), fitur baru untuk kualitas sinyal

#### V. Trading Expectancy Calculator

- **Sumber:** `https://github.com/82080038/belajar_saham/blob/main/trading_expectancy.py`
- **Mengapa perlu diambil:** Tidak ada kalkulasi expectancy di aplikasi ini. Modul ini menghitung metrik trading fundamental: (1) **Expectancy** = (WinRate × AvgWin) − (LossRate × AvgLoss) dalam satuan R, (2) **Profit Factor** = (WinRate × AvgWin) / (LossRate × AvgLoss), (3) **Breakeven Win Rate** = 1/(1+RR), (4) **Position Sizing** berdasarkan risk per trade dan stop loss, (5) **Simulasi trades** dengan fee, slippage, pajak — menghasilkan equity curve dan journal. Juga: `StockProfile` dataclass untuk profil karakteristik per emiten.
- **Cara adopsi:** **Raw copy** ke `src/trading_system/backtest/expectancy.py`. Murni Python stdlib (random, dataclasses). Gunakan untuk: evaluasi strategi di backtest, validasi risk-reward di Decision Engine, edukasi user di dashboard.
- **Estimasi usaha:** Rendah (raw copy, tidak ada dependency)
- **Mengatasi:** §3.2 (backtest metrics), §3.6 (risk-reward validation), §5.4 (strategy evaluation)

#### W. World Monitor — Global Intelligence Dashboard

- **Sumber:** `https://github.com/82080038/worldmonitor` (fork dari `koala73/worldmonitor`)
- **Mengapa perlu diambil:** Aplikasi ini punya `analysis/global_market.py` dan `analysis/macro.py` yang terbatas. WorldMonitor adalah dashboard intelligence real-time dengan: (1) **500+ news feeds** across 15 kategori, AI-synthesized into briefs, (2) **Country Instability Index (CII)** — stress scoring untuk 31 negara, (3) **Finance radar** — 29 bursa saham, komoditas, crypto, 7-signal market composite, (4) **Cross-stream correlation** — military, economic, disaster, escalation signal convergence, (5) **Local AI** (Ollama, no API keys), (6) **6 site variants** (world, tech, finance, commodity, happy, energy).
- **Cara adopsi:** **Referensi arsitektur**, bukan raw copy (Next.js + Tauri, beda stack dengan `global` yang Python/Next.js). Yang bernilai: (a) konsep 7-signal market composite untuk `macro.py`, (b) CII scoring untuk risk assessment geopolitik, (c) news feed aggregation pattern untuk `sentiment/engine.py`, (d) cross-stream correlation concept untuk `analysis/relationship.py`. Pelajari algoritma CII dan 7-signal composite, implementasi ulang di Python.
- **Estimasi usaha:** Tinggi (reverse engineer algoritma + re-implement di Python)
- **Mengatasi:** §4.1 (global market data), §5.4 (geopolitical risk), fitur baru macro intelligence

#### X. Factor Engine (7-Factor Cross-Sectional Scoring)

- **Sumber:** `C:\xampp\htdocs\TIP\python\engines\factor_engine.py` (407 baris)
- **Mengapa perlu diambil:** Aplikasi `global` tidak punya **factor-based scoring** — Decision Engine memakai weighted average technical+fundamental+macro+sentiment, bukan factor model. TIP mengimplementasikan 7 faktor profesional: (1) **Momentum** (1M/3M/6M/12M trailing returns), (2) **Value** (earnings yield proxy), (3) **Quality** (Sharpe-like return consistency), (4) **Low Volatility** (rolling 60-day realized vol), (5) **Beta** (rolling 60-day beta vs benchmark), (6) **Size** (market cap proxy = price × volume), (7) **Dividend Yield** (placeholder). Semua dengan **cross-sectional percentile rank**, **PIT-safe** (point-in-time filter), **liquidity filter** (min volume), dan **composite ranking**.
- **Cara adopsi:** Convert dari PostgreSQL → SQLite. Ganti `conn.cursor()` dengan `DataStorage` methods. Integrasikan ke `decision/engine.py` sebagai input alternatif/suplemen ke scoring yang sudah ada. Gunakan `^JKSE` sebagai benchmark (sudah tersedia via yfinance).
- **Estimasi usaha:** Sedang (convert DB layer + integrasi)
- **Mengatasi:** §2.4 (AI Learning kualitas), §5.4 (factor models), §4.6 (kualitas sinyal)

#### Y. Alpha Composer (Regime-Aware Composite Signal)

- **Sumber:** `C:\xampp\htdocs\TIP\python\engines\alpha_composer.py` (190 baris)
- **Mengapa perlu diambil:** Decision Engine `global` memakai conviction score 0–100 dari weighted average, tapi tidak ada **regime multiplier** yang formal. Alpha Composer: (1) ambil factor scores dari FactorEngine, (2) terapkan **regime multiplier** (bull=1.0, neutral=0.7, bear=0.2, crisis=0.0), (3) terapkan **sector multiplier**, (4) hitung **composite alpha** dengan confidence, (5) generate **reason codes** (LOW_ALPHA, LOW_CONFIDENCE, REGIME_GATE). Versioned (`ALPHA_VERSION = "1.0"`).
- **Cara adopsi:** **Raw copy** ke `src/trading_system/decision/alpha_composer.py`. Tidak ada dependency DB — menerima dict dari FactorEngine. Integrasi dengan Regime Detector (komponen F) dan Factor Engine (komponen X). Output sebagai input ke Decision Engine.
- **Estimasi usaha:** Rendah (raw copy, murni Python dataclass)
- **Mengatasi:** §4.6 (regime-aware conviction), §3.6 (regime-aware risk), §5.4 (alpha framework)

#### Z. No-Trade Engine (9-Gate Pre-Trade Filter)

- **Sumber:** `C:\xampp\htdocs\TIP\python\engines\no_trade.py` (213 baris)
- **Mengapa perlu diambil:** Decision Engine `global` tidak punya **no-trade gate** — semua sinyal dieksekusi selama action bukan HOLD. TIP punya 9 gate: (1) **Regime blocklist** (crisis/unknown = NO_TRADE), (2) **Low confidence**, (3) **Low composite alpha**, (4) **Low liquidity** (min volume), (5) **Insufficient history** (min 60 bars), (6) **Stale data** (max 7 hari), (7) **Event risk** (earnings/corporate action proximity), (8) **Model disagreement** (min 60% model agreement), (9) **Data quality failure**. Setiap gate menghasilkan reason code. Batch evaluation untuk seluruh universe.
- **Cara adopsi:** **Raw copy** ke `src/trading_system/decision/no_trade.py`. Murni Python dataclass, tidak ada dependency DB. Integrasi ke `decision/engine.py` — setelah `recommend()`, jalankan `NoTradeEngine.evaluate()` untuk setiap sinyal. Jika NO_TRADE, override action menjadi HOLD dengan reason codes.
- **Estimasi usaha:** Rendah (raw copy + integrasi ~1 jam)
- **Mengatasi:** §4.6 (kualitas sinyal), §3.6 (risk management), fitur baru pre-trade filter

#### AA. Cross-Asset Engine (Risk-On/Off Detection)

- **Sumber:** `C:\xampp\htdocs\TIP\python\engines\cross_asset.py` (236 baris)
- **Mengapa perlu diambil:** `global` punya `analysis/global_market.py` dan `analysis/macro.py` tapi tidak ada **cross-asset correlation analysis**. TIP menghitung: (1) **Rolling beta** equity vs DXY/VIX/rates (30-day window), (2) **Rolling correlation matrix** antar aset, (3) **Z-scores** per aset, (4) **Risk-on/off consistency score** — voting system: equity up + DXY down + VIX down = risk_on; sebaliknya = risk_off. Output: regime label (risk_on/risk_off/neutral) + confidence.
- **Cara adopsi:** Convert dari PostgreSQL → SQLite/`DataStorage`. Gunakan data dari `macro.py` (VIX, DXY, US10Y sudah di-fetch). Tambahkan USDIDR dan SP500/Nikkei/HangSeng dari `global_market.py`. Output sebagai input ke Regime Detector (komponen F).
- **Estimasi usaha:** Sedang (convert DB + integrasi dengan macro engine)
- **Mengatasi:** §4.1 (global market data), §4.6 (regime multi-indikator), §3.6 (cross-asset risk)

#### BB. Lead-Lag Analyzer (Cross-Correlation Research Tool)

- **Sumber:** `C:\xampp\htdocs\TIP\python\engines\lead_lag.py` (166 baris)
- **Mengapa perlu diambil:** Tidak ada analisis lead-lag di `global`. Modul ini: (1) **Cross-correlation** antar instrumen pada berbagai offset (−10 sampai +10 hari), (2) Identifikasi **leader vs follower** (saham yang bergerak lebih dulu), (3) **Significance test** (threshold korelasi 0.3), (4) Batch analysis untuk multiple pairs. Research tool untuk memahami rantai transmisi (mis: DXY → IHSG → saham individual).
- **Cara adopsi:** **Raw copy** ke `src/trading_system/analysis/lead_lag.py`. Murni numpy, tidak ada dependency DB. Integrasi dengan `analysis/relationship.py` yang sudah ada. Output: pasangan leader-follower + offset hari.
- **Estimasi usaha:** Rendah (raw copy, fungsi murni numpy)
- **Mengatasi:** Fitur baru, melengkapi analysis layer dengan analisis rantai transmisi

#### CC. Data Quality Engine (OHLCV Validation)

- **Sumber:** `C:\xampp\htdocs\TIP\python\ingestion\quality.py` (142 baris)
- **Mengapa perlu diambil:** `global` tidak punya **data quality checks** otomatis. TIP mendeteksi: (1) **Missing bars** (gap kalender bisnis), (2) **Duplicate timestamps**, (3) **Zero/negative prices**, (4) **High < low violations**, (5) **Stale data** (max 7 hari), (6) **Abnormal returns** (>25%). Output: `QualityReport` dengan `passed` property dan `summary()` dalam Bahasa Indonesia.
- **Cara adopsi:** **Raw copy** ke `src/trading_system/data/quality.py`. Murni pandas, tidak ada dependency DB. Jalankan setiap kali `DataStorage.load_ohlcv()` atau setelah fetch dari yfinance. Integrasi ke No-Trade Engine (komponen Z, Gate 9).
- **Estimasi usaha:** Rendah (raw copy + integrasi ke data pipeline)
- **Mengatasi:** §4.1 (data quality), §4.5 (konsolidasi indikator), §5.4 (data integrity)

#### DD. Rate Limiter dengan Circuit Breaker

- **Sumber:** `C:\xampp\htdocs\TIP\python\ingestion\rate_limit.py` (235 baris)
- **Mengapa perlu diambil:** `global` fetch data via yfinance tanpa rate limiting yang proper. TIP mengimplementasikan: (1) **Configurable delay** (min 2s, max 5s dengan jitter), (2) **Sliding window rate limit** (max 100 req/jam), (3) **Exponential backoff** (base 2s, max 60s), (4) **Circuit breaker** (5 consecutive failures → OPEN, reset 120s → HALF_OPEN), (5) **Per-symbol failure tracking**. Semua configurable via `.env`.
- **Cara adopsi:** **Raw copy** ke `src/trading_system/data/rate_limit.py`. Hanya dependency `python-dotenv` (sudah ada). Gunakan untuk semua yfinance calls di `data/fetcher.py`. Tambahkan env vars ke `.env.example`.
- **Estimasi usaha:** Rendah (raw copy + integrasi ke fetcher)
- **Mengatasi:** §4.1 (sumber data reliability), §5.3 (resilience), §8.3 (anti-ban)

#### EE. Alpha Validation Lab (Factor Testing Framework)

- **Sumber:** `C:\xampp\htdocs\TIP\python\engines\alpha_validation.py` (233 baris)
- **Mengapa perlu diambil:** Tidak ada framework untuk **validasi alpha factor** sebelum produksi di `global`. TIP mengimplementasikan workflow: hypothesis → experiment config → result → **VALID/WATCH/REJECT**. Thresholds: min Sharpe 0.5, min Sortino 0.7, min Calmar 0.3, max drawdown 25%, min hit rate 45%, min OOS Sharpe 0.3, min robustness 0.6, max turnover 2.0. Test: OOS performance (walk-forward), parameter robustness, regime segmentation, leakage test, survivorship test, cost-adjusted returns.
- **Cara adopsi:** **Raw copy** ke `src/trading_system/backtest/alpha_validation.py`. Murni numpy + dataclass. Integrasi dengan Walk-Forward Validator (komponen D) dan Factor Engine (komponen X). Gunakan untuk menvalidasi setiap factor sebelum masuk ke Alpha Composer.
- **Estimasi usaha:** Rendah (raw copy + integrasi)
- **Mengatasi:** §5.4 (strategy versioning & leaderboard), §3.2 (backtest metrics), §2.4 (AI Learning validasi)

#### FF. Enhanced Risk Engine (Vol-Targeted + Drawdown Guard)

- **Sumber:** `C:\xampp\htdocs\TIP\python\engines\risk_engine.py` (327 baris)
- **Mengapa perlu diambil:** Risk engine `global` (`risk/engine.py`) punya position sizing dasar. TIP jauh lebih advanced: (1) **Volatility-targeted position sizing** (inverse vol × alpha score), (2) **Regime-aware cash allocation** (crisis=50% cash, bear=30%, neutral=15%, bull=5%), (3) **Sector exposure caps** (max 30% per sector), (4) **Max portfolio beta** guard (1.3), (5) **Drawdown guard** (10% threshold), (6) **Stop-loss + trailing stop** policy (8% SL, 12% trailing), (7) **Transaction cost estimate** (15 bps + 10 bps slippage = Indonesia rates), (8) **Portfolio-level risk metrics** (vol, beta, gross/net exposure, sector exposure).
- **Cara adopsi:** Convert ke `src/trading_system/risk/engine.py` (replace/expand existing). Murni numpy + dataclass, tidak ada dependency DB. Integrasi dengan Alpha Composer (komponen Y) untuk input signals, Regime Detector (F) untuk regime state, dan Correlation Manager (I) untuk correlation penalty.
- **Estimasi usaha:** Sedang (replace + integrasi dengan multiple engines)
- **Mengatasi:** §3.6 (portfolio VaR, regime-aware risk, drawdown guard), §4.5 (transaction cost), §5.4 (risk management)

### 9.3 Komponen Prioritas Rendah — Nice-to-Have

#### O. ESG & Corporate Governance Scraper

- **Sumber:** `C:\xampp\htdocs\data_pasar_modal\ai_engine\scrape_idx_esg_governance.py` (355 baris)
- **Mengapa perlu diambil:** Tidak ada data ESG/governance di aplikasi ini. Scraper ini ekstrak dari annual report PDF: MSCI rating (AAA–CCC), S&P Global CSA score, FTSE4Good, Refinitiv, ASEAN Corporate Governance Scorecard, board composition, independent commissioners, audit committee.
- **Cara adopsi:** Convert MySQL → SQLite. Buat tabel `esg_scores` dan `corporate_governance` via Alembic. Tambahkan ESG score sebagai faktor di fundamental analysis (sudah ada `red_flags.py` yang bisa diperluas).
- **Estimasi usaha:** Sedang (PDF parsing + convert DB)
- **Mengatasi:** Fitur baru, melengkapi fundamental dengan governance

#### P. Email Notification (Fallback Telegram)

- **Sumber:** `K:\xampp\htdocs\swing\modules\alert_notifier.py` (208 baris, bagian `_send_email`)
- **Mengapa perlu diambil:** §5.3 menyebutkan "alert bukan hanya Telegram: fallback email/webhook bila Telegram gagal". Implementasi email sudah ada di swing: SMTP dengan `smtplib`, format MIME, starttls.
- **Cara adopsi:** Extract fungsi `_send_email` dan `_init_email`, tambahkan ke sistem notifikasi aplikasi ini (saat ini Telegram di `decision/engine.py`). Buat `utils/notifier.py` terpusat dengan Telegram + Email + fallback logging.
- **Estimasi usaha:** Rendah
- **Mengatasi:** §5.3 (alert fallback), §5.3 (kegagalan notifikasi tidak terlihat)

#### Q. Stock Screener Multi-Kriteria (Breakout + Oversold)

- **Sumber:** `K:\xampp\htdocs\swing\modules\stock_screener.py` (216 baris)
- **Mengapa perlu diambil:** Aplikasi ini sudah punya `analysis/screener.py` dengan template technical/momentum/value. Swing punya tambahan: **breakout detection** (price > recent high × 1.02), **oversold screening** (uptrend + RSI oversold + volume confirmation), **liquidity filter** (min nilai transaksi harian).
- **Cara adopsi:** Tambahkan template `breakout` dan `oversold` ke `screener.py` yang sudah ada. Adaptasi ke DataFrame format `global` (sudah menggunakan pandas).
- **Estimasi usaha:** Rendah
- **Mengatasi:** §8.4 #1 (screener multi-kriteria), §8.2 (Stockbit-style screener)

#### R. IDX API Integration Guide (Referensi)

- **Sumber:** `C:\xampp\htdocs\data_pasar_modal\IDX_API_GUIDE.md` (558 baris)
- **Mengapa perlu diambil:** Dokumen komprehensif tentang semua opsi API data IDX: (1) RapidAPI IDX (gratis 500 req/bulan, $25/bulan 10K req), (2) OHLC.dev ($15/bulan), (3) GitHub scrapers (gratis, risky), (4) Yahoo Finance (current). Termasuk strategi anti-ban (exponential backoff, request queue, caching, proxy rotation, usage monitoring) dengan contoh kode JavaScript dan Python.
- **Cara adopsi:** Copy sebagai referensi ke `docs/IDX_API_GUIDE.md`. Gunakan sebagai panduan saat implementasi `DataSourceAdapter` (§4.1). Pattern rate limiting dan caching bisa langsung diadopsi.
- **Estimasi usaha:** Rendah (copy dokumen + implementasi pattern)
- **Mengatasi:** §4.1 (sumber data alternatif), §8.3 (sumber data IDX profesional)

### 9.4 Ringkasan Prioritas Adopsi

| # | Komponen | Sumber Repo | Estimasi Usaha | Mengatasi § | Prioritas |
|---|----------|-------------|----------------|------------|-----------|
| A | IDX Foreign Flow Scraper | data_pasar_modal | Rendah–Sedang | §4.1, §8.2, §8.3 | **Tinggi** |
| B | IDX Broker Summary Scraper | data_pasar_modal | Rendah–Sedang | §4.1, §8.2, §8.3 | **Tinggi** |
| C | Purged Time Series Split | ML | Rendah | §2.4, §5.4 | **Tinggi** |
| D | Walk-Forward Validator | ML | Rendah | §3.2, §5.4 | **Tinggi** |
| E | Stateful Paper Trading | swing | Sedang | §8.4 #3 | **Tinggi** |
| F | Enhanced Regime Detector | pasar_modal | Sedang | §4.6, §3.6 | **Tinggi** |
| G | IDX Fundamental Scraper (PDF) | data_pasar_modal | Sedang | §4.1 | **Tinggi** |
| H | Performance Attribution | swing | Sedang | §5.4 | Menengah |
| I | Correlation-Based Position Sizing | swing | Sedang | §3.6, §4.5 | Menengah |
| J | Sector-Specific Metrics | pasar_modal | Sedang | §5.4 | Menengah |
| K | Advanced Technical (Ichimoku+PSAR) | pasar_modal | Rendah | §4.5, §4.6 | Menengah |
| L | Model Registry + Monitor | ML | Sedang | §2.4, §5.4 | Menengah |
| M | Manipulation Detector | swing | Sedang–Tinggi | Fitur baru | Menengah |
| N | Alpha-Adjusted Labeling | ML | Rendah | §2.4, §5.4 | Menengah |
| O | ESG/Governance Scraper | data_pasar_modal | Sedang | Fitur baru | Rendah |
| P | Email Notification | swing | Rendah | §5.3 | Rendah |
| Q | Screener Breakout+Oversold | swing | Rendah | §8.4 #1 | Rendah |
| R | IDX API Guide (referensi) | data_pasar_modal | Rendah | §4.1, §8.3 | Rendah |
| S | Deep Learning (LSTM/GRU/Transformer) | trading-otomatis-indonesia (GitHub) | Sedang | §2.4, §5.4 | **Tinggi** |
| T | Ensemble System (Voting+Stacking) | trading-otomatis-indonesia (GitHub) | Sedang | §2.4, §5.4 | **Tinggi** |
| U | Order Book Analyzer (Gap+S/R) | trading-otomatis-indonesia (GitHub) | Rendah | §4.5 | Menengah |
| V | Trading Expectancy Calculator | belajar_saham (GitHub) | Rendah | §3.2, §3.6 | Menengah |
| W | World Monitor (referensi arsitektur) | worldmonitor (GitHub) | Tinggi | §4.1, §5.4 | Rendah |
| X | Factor Engine (7 faktor) | TIP | Sedang | §2.4, §5.4, §4.6 | **Tinggi** |
| Y | Alpha Composer (regime-aware) | TIP | Rendah | §4.6, §3.6, §5.4 | **Tinggi** |
| Z | No-Trade Engine (9 gates) | TIP | Rendah | §4.6, §3.6 | **Tinggi** |
| AA | Cross-Asset Engine (risk-on/off) | TIP | Sedang | §4.1, §4.6, §3.6 | Menengah |
| BB | Lead-Lag Analyzer | TIP | Rendah | Fitur baru | Menengah |
| CC | Data Quality Engine | TIP | Rendah | §4.1, §4.5, §5.4 | **Tinggi** |
| DD | Rate Limiter + Circuit Breaker | TIP | Rendah | §4.1, §5.3, §8.3 | **Tinggi** |
| EE | Alpha Validation Lab | TIP | Rendah | §5.4, §3.2, §2.4 | Menengah |
| FF | Enhanced Risk Engine (vol-targeted) | TIP | Sedang | §3.6, §4.5, §5.4 | **Tinggi** |

### 9.5 Peta Integrasi — Ke Mana Setiap Komponen Masuk

```
src/trading_system/
├── analysis/
│   ├── regime.py              ← (F) Enhanced Regime Detector [REPLACE]
│   ├── advanced_technical.py  ← (K) Ichimoku + Parabolic SAR [NEW]
│   ├── sector_metrics.py      ← (J) JASICA sector metrics [NEW]
│   ├── manipulation_detector.py ← (M) Pump/dump/spoofing [NEW]
│   ├── order_book.py          ← (U) Gap + Support/Resistance [NEW]
│   ├── cross_asset.py         ← (AA) Cross-asset risk-on/off [NEW]
│   ├── factor_engine.py       ← (X) 7-factor cross-sectional scoring [NEW]
│   └── screener.py            ← (Q) Tambah template breakout+oversold [EDIT]
├── ai_learning/
│   ├── purged_cv.py           ← (C) Purged TimeSeriesSplit [NEW]
│   ├── labeling.py            ← (N) Alpha-adjusted labeling [NEW]
│   ├── model_registry.py      ← (L) Model versioning [NEW]
│   ├── model_monitor.py       ← (L) Drift detection [NEW]
│   ├── deep_learning.py       ← (S) LSTM/GRU/Transformer [NEW]
│   └── ensemble.py            ← (T) Voting+Stacking ensemble [NEW]
├── backtest/
│   ├── walk_forward.py        ← (D) Walk-forward validator [NEW]
│   ├── expectancy.py          ← (V) Trading expectancy calculator [NEW]
│   └── alpha_validation.py    ← (EE) Alpha validation lab [NEW]
├── data/
│   ├── idx_foreign_flow_scraper.py ← (A) Real foreign flow [NEW]
│   ├── idx_broker_flow_scraper.py  ← (B) Real broker summary [NEW]
│   ├── idx_fundamental_scraper.py  ← (G) Annual report PDF [NEW]
│   ├── quality.py             ← (CC) Data quality engine [NEW]
│   └── rate_limit.py          ← (DD) Rate limiter + circuit breaker [NEW]
├── paper_trading/
│   └── engine.py              ← (E) Stateful paper trading [REPLACE/EXPAND]
├── portfolio/
│   └── attribution.py         ← (H) Performance attribution [NEW]
├── decision/
│   ├── engine.py              ← existing
│   ├── alpha_composer.py      ← (Y) Alpha composer [NEW]
│   └── no_trade.py            ← (Z) No-trade engine [NEW]
├── risk/
│   └── engine.py              ← (FF) Vol-targeted + drawdown guard [REPLACE] + (I) Correlation sizing [EDIT]
├── sentiment/
│   ├── foreign_flow.py        ← (A) Gunakan real data [EDIT]
│   └── broker_summary.py      ← (B) Gunakan real data [EDIT]
└── utils/
    └── notifier.py            ← (P) Email fallback [NEW]

docs/
└── IDX_API_GUIDE.md           ← (R) Referensi API IDX [NEW]
```

### 9.6 Urutan Implementasi yang Disarankan

**Fase 1 — Quick wins (1–2 minggu):**
1. (C) Purged Time Series Split → raw copy, integrasi ke AI Learning
2. (D) Walk-Forward Validator → raw copy, siap untuk ConvictionStrategy
3. (K) Advanced Technical Indicators → raw copy
4. (N) Alpha-Adjusted Labeling → raw copy, integrasi ke AI Learning
5. (P) Email Notification → extract dari swing, tambah ke notifier
6. (Q) Screener breakout+oversold → tambah template ke screener.py
7. (U) Order Book Analyzer → raw copy dari GitHub, fungsi murni
8. (V) Trading Expectancy Calculator → raw copy dari GitHub, fungsi murni
9. (Y) Alpha Composer → raw copy dari TIP, murni dataclass
10. (Z) No-Trade Engine → raw copy dari TIP, murni dataclass
11. (CC) Data Quality Engine → raw copy dari TIP, murni pandas
12. (DD) Rate Limiter → raw copy dari TIP, integrasi ke fetcher
13. (EE) Alpha Validation Lab → raw copy dari TIP, murni numpy

**Fase 2 — Data riil IDX (2–4 minggu):**
1. (A) IDX Foreign Flow Scraper → convert MySQL→SQLite, integrasi
2. (B) IDX Broker Summary Scraper → convert MySQL→SQLite, integrasi
3. (G) IDX Fundamental Scraper → convert, tambah pdfplumber
4. (R) IDX API Guide → copy sebagai referensi

**Fase 3 — Engine upgrades (1–2 bulan):**
1. (F) Enhanced Regime Detector → replace regime.py, integrasi macro
2. (E) Stateful Paper Trading → expand paper_trading/engine.py
3. (L) Model Registry + Monitor → integrasi AI Learning
4. (I) Correlation-Based Position Sizing → integrasi risk engine
5. (H) Performance Attribution → modul baru + endpoint API
6. (S) Deep Learning Models → convert dari GitHub, integrasi AI Learning
7. (T) Ensemble System → convert dari GitHub, integrasi AI Learning
8. (X) Factor Engine → convert dari TIP (PostgreSQL→SQLite), integrasi decision
9. (FF) Enhanced Risk Engine → replace risk/engine.py dengan TIP version
10. (AA) Cross-Asset Engine → convert dari TIP, integrasi dengan macro

**Fase 4 — Fitur lanjutan (berkelanjutan):**
1. (J) Sector-Specific Metrics → butuh data dari (G)
2. (M) Manipulation Detector → butuh ML training
3. (O) ESG/Governance Scraper → butuh PDF parsing
4. (W) World Monitor patterns → reverse engineer 7-signal composite & CII untuk macro intelligence
5. (BB) Lead-Lag Analyzer → raw copy dari TIP, integrasi intelligence layer

### 9.7 Catatan Teknis Adopsi

- **Konversi database:** Semua scraper di `data_pasar_modal` memakai MySQL via `subprocess.run(['/opt/lampp/bin/mysql', ...])`. Untuk adopsi ke `global` (SQLite), ganti dengan `sqlite3` atau `sqlalchemy` yang sudah dipakai di `data/storage.py`. Hapus dependency `cloudscraper`, ganti dengan `httpx` (sudah di `pyproject.toml`). Tambahkan `User-Agent` header dan retry logic.
- **Konversi import path:** Modul `swing` memakai `from modules.xxx import Yyy` dan `from utils.database_helper import db_helper`. Untuk adopsi, ubah ke `from trading_system.xxx import Yyy` dan gunakan `DataStorage` dari `data/storage.py`.
- **Konversi config:** `swing` memakai `from config import STRATEGY_CONFIG, TELEGRAM_CONFIG, ...`. Ubah ke `trading_system.config` yang sudah ada, atau tambahkan key baru ke `config.py`.
- **Dependency baru:** `pdfplumber` (untuk G, O), `mlflow` opsional (untuk L, fallback file-based sudah ada), `python-telegram-bot` (untuk P, opsional jika Telegram dua arah §8.4 #4), `tensorflow` (untuk S, opsional dengan flag `DL_AVAILABLE`), `scikit-learn` sudah ada (untuk T, U, V).
- **Repo GitHub yang belum di-clone lokal:** `trading-otomatis-indonesia`, `AI_Trading`, `belajar_saham`, `worldmonitor` — perlu `git clone` ke komputer ini sebelum adopsi. `bandarmologi` hanya README (kosong, tidak ada kode). Repo `saham` (submodule `belajar_saham`) mengembalikan 404 (private atau dihapus).
- **TIP (Trading Intelligence Platform):** Repo lokal `C:\xampp\htdocs\TIP\` — 8 fase lengkap, 300 tests passing, PostgreSQL+TimescaleDB. Semua modul TIP memakai PostgreSQL via `psycopg2` — untuk adopsi ke `global` (SQLite), ganti dengan `DataStorage` dari `data/storage.py`. TIP punya 17 modul Python di `python/engines/` + 8 modul di `python/ingestion/` + FastAPI 14 endpoints + 13 file dokumentasi. Yang bernilai untuk adopsi: factor engine, alpha composer, no-trade engine, cross-asset, lead-lag, data quality, rate limiter, alpha validation, risk engine (komponen X–FF).
- **Drive yang tidak relevan:** `D:\` hanya berisi game (PointBlank). `L:\` berisi file personal (dokumen, foto, backup HP) — tidak ada kode trading.
- **Tes:** Setiap komponen yang diadopsi harus disertai unit test di `tests/unit/`. Untuk scraper, gunakan mock HTTP (mis. `respx` atau `pytest-httpx`). Untuk modul kuantitatif (C, D, N), tes dengan data sintetik yang known-answer.

---

## 10. Ringkasan Pemeriksaan Lengkap

> **Tanggal:** 1 Agustus 2026
> **Tujuan:** Mendokumentasikan seluruh sumber yang diperiksa untuk memastikan tidak ada repo, drive, atau data yang terlewat.

### 10.1 Sumber yang Diperiksa

| # | Sumber | Lokasi | Hasil |
|---|--------|--------|-------|
| 1 | HDD `C:\xampp\htdocs\` | 25+ folder | Ditemukan: `pasar_modal`, `data_pasar_modal`, `TIP`, `global` + repo non-trading (bimbel, chat, restoran, EBP, dashboard, dll.) |
| 2 | HDD `K:\xampp\htdocs\` | 25+ folder | Ditemukan: `swing`, `ML` + repo non-trading (RISK = risk assessment objek wisata, plan, meta, dagang, koperasi, dll.) |
| 3 | HDD `D:\` | Root | Hanya game (PointBlank ID). Tidak ada kode trading. |
| 4 | HDD `L:\` | Root | File personal (dokumen, foto, backup HP). Tidak ada kode trading. |
| 5 | GitHub page 1 | `github.com/82080038?tab=repositories&page=1` | Ditemukan: `trading-otomatis-indonesia`, `AI_Trading`, `databases` |
| 6 | GitHub page 2 | `github.com/82080038?tab=repositories&page=2` | Ditemukan: `belajar_saham`, `worldmonitor`, `bandarmologi` |
| 7 | GitHub page 3 | `github.com/82080038?tab=repositories&page=3` | Tidak ada repo trading (Mitra-Bukalapak, speech-to-text, wilayah Indonesia, dll.) |
| 8 | GitHub submodule | `github.com/82080038/saham` | 404 (private atau dihapus) — submodule dari `belajar_saham` |

### 10.2 Repository yang Relevan dengan Trading (9 repo)

| Repository | Lokasi | Komponen di §9 |
|-----------|--------|----------------|
| **pasar_modal** | `C:\xampp\htdocs\pasar_modal\` | F, J, K |
| **swing** | `K:\xampp\htdocs\swing\` | E, H, I, M, P, Q |
| **ML** | `K:\xampp\htdocs\ML\` | C, D, L, N |
| **data_pasar_modal** | `C:\xampp\htdocs\data_pasar_modal\` | A, B, G, O, R |
| **TIP** | `C:\xampp\htdocs\TIP\` | X, Y, Z, AA, BB, CC, DD, EE, FF |
| **trading-otomatis-indonesia** | GitHub | S, T, U |
| **belajar_saham** | GitHub | V |
| **worldmonitor** | GitHub | W (referensi arsitektur) |
| **bandarmologi** | GitHub | — (kosong, hanya README) |

### 10.3 Repository yang Tidak Relevan

| Repository | Alasan |
|-----------|--------|
| `RISK` (K:\) | Risk assessment objek wisata, bukan trading |
| `plan` (K:\) | Planner app, bukan trading |
| `meta` (K:\) | Meta/API app, bukan trading |
| `databases` (GitHub) | KSP cooperative financial management, bukan trading |
| `AI_Trading` (GitHub) | Sudah dicatat di §9.0 tapi belum diekstrak komponennya (XAMPP-based, perlu clone untuk analisa lebih dalam) |
| 87 repo GitHub lainnya | Non-trading (wilayah Indonesia, e-commerce, PHP libraries, dll.) |

---

## 11. Data & Database — Adopsi ke Aplikasi Ini

> **Temuan kunci:** Ada data historis IDX yang signifikan di `data_pasar_modal` (MySQL export, 47 tabel dengan data) dan `swing` (SQLite, 46K+ rows price data) yang belum ada di `global`. Aplikasi `global` sudah punya 1.37 juta rows OHLCV tapi **kosong** untuk fundamental, macro, foreign flow, corporate actions, ESG, dll.

### 11.1 Database yang Ditemukan

| Database | Lokasi | Ukuran | Format | Tabel berdata |
|----------|--------|--------|--------|---------------|
| **data_pasar_modal** | `C:\xampp\htdocs\data_pasar_modal\database_export\` | ~284KB + 232KB | MySQL dump (.sql) | 47 dari 58 tabel |
| **swing_trading.db** | `K:\xampp\htdocs\swing\swing_trading.db` | 843KB | SQLite | 7 dari 12 tabel |
| **ml_trading.db** | `K:\xampp\htdocs\ML\ml_trading.db` | 364KB | SQLite | 1 tabel |
| **TIP schema** | `C:\xampp\htdocs\TIP\database\migrations\` | 30KB | PostgreSQL (.sql) | Schema only + seeds |
| **TIP instruments** | `C:\xampp\htdocs\TIP\database\seeds\instruments.csv` | 3KB | CSV | 37 instrumen |
| **trading_system.db** | `C:\xampp\htdocs\global\data\trading_system.db` | 216MB | SQLite | 2 dari 15 tabel berdata |

### 11.2 Data yang Perlu Diambil ke Aplikasi Ini

#### Prioritas Tinggi — Data unik yang tidak ada di `global`

| # | Data | Sumber | Estimasi rows | Cara adopsi | Disimpan ke |
|---|------|--------|---------------|-------------|-------------|
| **D1** | Makroekonomi (BI Rate, inflasi, GDP, USD/IDR, 2001–2026) | `data_pasar_modal.sql` → `makroekonomi` | 379 | Parse SQL INSERT → DataFrame → `to_sql` | SQLite `macro_data` + parquet `data/clean/macro.parquet` |
| **D2** | Master saham (kode, nama, sektor, PER, PBV, ROE, DER, market_cap) | `data_pasar_modal.sql` → `saham` | ~50-100 | Parse SQL → import | SQLite `instrument_master` + parquet `data/clean/instruments.parquet` |
| **D3** | Fundamental kuartalan (revenue, net_profit, EPS, NPM, growth) | `data_pasar_modal.sql` → `saham_fundamental` | ~200+ | Parse SQL → import | SQLite `fundamental_data` + parquet `data/clean/fundamental.parquet` |
| **D4** | Foreign flow (foreign buy/sell per saham) | `data_pasar_modal.sql` → `foreign_flow` | ~1000+ | Parse SQL → import | SQLite `foreign_flow` + parquet `data/clean/foreign_flow.parquet` |
| **D5** | Broker flow (broker summary market-wide) | `data_pasar_modal.sql` → `broker_flow` | ~500+ | Parse SQL → import | SQLite `broker_flow` + parquet `data/clean/broker_flow.parquet` |
| **D6** | IHSG history (index daily) | `data_pasar_modal.sql` → `ihsg_history` | ~5000+ | Parse SQL → import | SQLite `ohlcv` (ticker=`^JKSE`) |
| **D7** | Bursa global (S&P500, Nikkei, HangSeng, dll.) | `data_pasar_modal.sql` → `bursa_global` | ~5000+ | Parse SQL → import | SQLite `ohlcv` (ticker=index) |
| **D8** | Komoditas (gold, oil, dll.) | `data_pasar_modal.sql` → `komoditas` | ~3000+ | Parse SQL → import | SQLite `ohlcv` (ticker=commodity) |
| **D9** | Kebijakan & regulasi (BI, OJK, BEI, DPR) | `data_pasar_modal.sql` → `kebijakan_regulasi` | ~100+ | Parse SQL → import | SQLite `policy_events` + parquet |
| **D10** | Aksi korporasi (dividen, split, buyback, right issue) | `data_pasar_modal.sql` → `aksi_korporasi` | ~200+ | Parse SQL → import | SQLite `corporate_actions` (sudah ada, 0 rows) |
| **D11** | Dividend history | `data_pasar_modal.sql` → `dividend` | ~100+ | Parse SQL → import | SQLite `dividends` + parquet |
| **D12** | Sektor klasifikasi | `data_pasar_modal.sql` → `sektor` | ~10 | Parse SQL → import | SQLite `sector_master` |
| **D13** | Market calendar | `data_pasar_modal.sql` → `market_calendar` | ~250 | Parse SQL → import | SQLite `market_calendar` |
| **D14** | Fear & Greed Index | `data_pasar_modal.sql` → `fear_greed_index` | ~100+ | Parse SQL → import | SQLite `fear_greed` + parquet |
| **D15** | Event eksternal | `data_pasar_modal.sql` → `event_eksternal` | ~50+ | Parse SQL → import | SQLite `external_events` + parquet |

#### Prioritas Menengah — Data berguna untuk validasi/enrichment

| # | Data | Sumber | Estimasi rows | Cara adopsi | Disimpan ke |
|---|------|--------|---------------|-------------|-------------|
| **D16** | ESG scores | `data_pasar_modal.sql` → `esg_scores` | ~50+ | Parse SQL → import | SQLite `esg_scores` + parquet |
| **D17** | Corporate governance | `data_pasar_modal.sql` → `corporate_governance` | ~50+ | Parse SQL → import | SQLite `corporate_governance` + parquet |
| **D18** | Stock personality profiles | `data_pasar_modal.sql` → `stock_personality` | ~50+ | Parse SQL → import | SQLite `stock_personality` + parquet |
| **D19** | Berita & sentiment | `data_pasar_modal.sql` → `berita_sentimen` | ~500+ | Parse SQL → import | SQLite `news` (sudah ada, 0 rows) + parquet |
| **D20** | AI scores (historical) | `data_pasar_modal.sql` → `ai_scores` | ~500+ | Parse SQL → import | SQLite `scores` (sudah ada, 0 rows) — sebagai baseline |
| **D21** | AI alerts (historical) | `data_pasar_modal.sql` → `ai_alerts` | ~48 | Parse SQL → import | SQLite `audit_log` atau tabel baru `alerts` |
| **D22** | Backtest results | `data_pasar_modal.sql` → `backtest_result` | ~50+ | Parse SQL → import | SQLite `backtest_results` + parquet |
| **D23** | Trade journal | `data_pasar_modal.sql` → `trade_journal` | ~50+ | Parse SQL → import | SQLite `trade_journal` + parquet |
| **D24** | Pattern analysis | `data_pasar_modal.sql` → `pattern_analysis` | ~100+ | Parse SQL → import | SQLite `pattern_analysis` + parquet |
| **D25** | Valuation cache | `data_pasar_modal.sql` → `valuation_cache` | ~100+ | Parse SQL → import | SQLite `valuation_cache` |

#### Prioritas Rendah — Data dari swing/ML/TIP

| # | Data | Sumber | Estimasi rows | Cara adopsi | Disimpan ke |
|---|------|--------|---------------|-------------|-------------|
| **D26** | Technical indicators (pre-computed) | `swing_trading.db` → `technical_indicators` | 23,469 | Import langsung SQLite→SQLite | SQLite `technical_indicators` (tabel baru) atau parquet `data/clean/tech_indicators.parquet` |
| **D27** | Fundamental data (swing) | `swing_trading.db` → `fundamental_data` | 21 | Import langsung | Merge ke D3 |
| **D28** | Stocks master (swing, 25 saham dengan sector/industry) | `swing_trading.db` → `stocks_master` | 25 | Import langsung | Merge ke D2 |
| **D29** | Stock prices (ML) | `ml_trading.db` → `stock_prices` | 4,720 | Import langsung | Merge ke `ohlcv` (cek duplikat) |
| **D30** | Instrument master (TIP, 37 instrumen + yfinance symbols) | `TIP\database\seeds\instruments.csv` | 37 | Import CSV langsung | SQLite `instrument_master` + parquet `data/clean/instruments_tip.parquet` |
| **D31** | TIP schema (PostgreSQL → SQLite reference) | `TIP\database\migrations\V001__initial_schema.sql` | Schema | Referensi untuk schema design | — (referensi saja) |

### 11.3 Strategi Penyimpanan: Parquet + SQLite

```
data/
├── raw/                           # MySQL dump asli (archive)
│   ├── data_pasar_modal.sql       # MySQL export asli
│   └── postgresql_data_pasar_modal.sql
├── clean/                         # Data yang sudah di-parse → parquet
│   ├── macro.parquet              # (D1) Makroekonomi 20+ tahun
│   ├── instruments.parquet        # (D2+D28+D30) Master saham merged
│   ├── fundamental.parquet        # (D3+D27) Fundamental merged
│   ├── foreign_flow.parquet       # (D4) Foreign flow
│   ├── broker_flow.parquet        # (D5) Broker flow
│   ├── policy_events.parquet      # (D9) Kebijakan regulasi
│   ├── corporate_actions.parquet  # (D10) Aksi korporasi
│   ├── dividends.parquet          # (D11) Dividend
│   ├── esg_scores.parquet         # (D16) ESG
│   ├── governance.parquet         # (D17) Corporate governance
│   ├── fear_greed.parquet         # (D14) Fear & Greed
│   ├── news_sentiment.parquet     # (D19) Berita & sentiment
│   ├── tech_indicators.parquet    # (D26) Technical indicators
│   └── ...                        # Parquet per tabel
├── archive/                       # Parquet per-tanggal (snapshot historis)
│   └── 2026-08-01/
│       ├── macro.parquet
│       └── ...
└── trading_system.db              # SQLite untuk active use (query, API)
```

**Prinsip:**
- **Parquet** = archive historis, columnar, kompresi efisien, untuk analisa offline (pandas/polars)
- **SQLite** = active use, API serving, real-time query
- **Raw** = MySQL dump asli (jangan dihapus, sebagai backup)
- **Clean** = parquet hasil parse (dibaca oleh `data/storage.py`)
- **Archive** = snapshot per-tanggal untuk retensi historis

### 11.4 Implementasi Import Data

> **PENTING:** Data sudah di-export ke Parquet di Sprint 3! Lihat §11.4a.

#### 11.4a Parquet Archive Sudah Ada (Sprint 3 — selesai)

Sprint 3 sudah mengeksekusi export seluruh data legacy ke Parquet:

- **Lokasi:** `K:\trading_data\raw\` (174 files, ~33 MB)
- **Script:** `scripts/export_mysql_to_parquet.py` + `scripts/export_sqlite_to_parquet.py`
- **Tabel ter-export (50+ folder):** `macro`, `saham`, `saham_historical`, `fundamental`, `foreign_flow`, `broker_flow`, `ihsg`, `global`, `commodity`, `corporate_action`, `corporate_governance`, `esg_scores`, `event_eksternal`, `fear_greed_index`, `kebijakan_regulasi`, `sektor`, `indikator_teknikal`, `technical`, `ai_scores`, `ai_alerts`, `backtest_result`, `trade_journal`, `pattern_analysis`, `portfolio`, `sentiment`, `stock_ipo`, `stock_personality`, `training_log`, `transaksi`, `mm_instrument`, `mm_security`, `mm_listing`, `mm_exchange`, `mm_issuer`, `sqlite_ohlcv`, `sqlite_macro_data`, `sqlite_global_market_data`, `sqlite_instruments`, `di_ohlcv_daily`, `ohlcv`, `multi_asset`, `blind_forecast`, `chart_patterns`, `data_fetch_log`, `ml_config`, `notifications`, `price_alerts`, `strategy_config`, `trader_saldo`, `ai_auto_trade`, `ai_correlation`, `ai_portfolio`
- **Config:** `DATA_ARCHIVE_DIR` env var + `ArchiveAdapter` untuk baca/tulis

**Status:** Data sudah dalam format Parquet siap pakai. Langkah berikutnya adalah **import dari Parquet ke SQLite** (bukan dari MySQL dump lagi).

#### 11.4b Langkah Import Parquet → SQLite

**Script:** `scripts/import_legacy_data.py` (baru)

**Langkah:**
1. Baca Parquet dari `K:\trading_data\raw\{tabel}\` via `ArchiveAdapter` (sudah ada)
2. Konversi schema Parquet → schema SQLite `global` (mapping kolom)
3. Cek duplikat vs `ohlcv` yang sudah ada (1.37M rows) — jangan overwrite
4. Import ke SQLite `trading_system.db` (tabel baru jika perlu, via Alembic migration)
5. Validasi: row count, date range, null check

**Estimasi usaha:** 1–2 hari (Parquet sudah ter-struktur, tinggal mapping + import)

**Catatan:** Estimasi turun dari 2–3 hari menjadi 1–2 hari karena data sudah dalam Parquet (tidak perlu parse SQL dump).

**Mengapa parquet juga?**
- §4.2 sudah mencatat: "File parquet raw zone menumpuk tanpa retensi" — parquet sudah menjadi bagian arsitektur `global`
- Data dari `data_pasar_modal` adalah snapshot historis (tidak akan berubah) → cocok untuk parquet
- Parquet memungkinkan analisa offline dengan polars/duckdb tanpa load ke SQLite
- Backup yang lebih compact dari SQL dump

### 11.5 Data yang Sudah Ada di `global` (tidak perlu import)

| Tabel | Rows | Catatan |
|-------|------|---------|
| `ohlcv` | 1,371,286 | Sudah punya price data lengkap — D6, D7, D8, D29 mungkin overlap, perlu cek duplikat |
| `watchlist` | 359 | Sudah ada |
| `scores` | 0 | Schema sudah ada, siap diisi (D20) |
| `corporate_actions` | 0 | Schema sudah ada, siap diisi (D10) |
| `news` | 0 | Schema sudah ada, siap diisi (D19) |
| `positions` | 0 | Schema sudah ada |
| `orders` | 0 | Schema sudah ada |
| `audit_log` | 0 | Schema sudah ada |

---

## 12. Rekomendasi Strategi — Base Development & Adopsi

> **Kesimpulan analisa komparatif 9 repository trading:** `global` adalah aplikasi paling unggul dan cocok untuk dikembangkan. TIP adalah sumber adopsi terkaya untuk meningkatkan kualitas quant engine.

### 12.1 Mengapa `global` Dipilih sebagai Base Development

| Kriteria | `global` | TIP | swing | ML | pasar_modal | data_pasar_modal | trading-otomatis | AI_Trading | belajar_saham |
|----------|----------|-----|-------|-----|-------------|------------------|------------------|------------|---------------|
| **Stack** | Next.js + FastAPI + SQLite | PHP + FastAPI + PostgreSQL | CLI | — | Streamlit | PHP web | PHP + Python | PHP web | CLI |
| **Modul lengkap** | 18 engines | ~10 engines | 6 modul | 4 modul | Blueprint | Scraper | 44+ modul | — | 1 modul |
| **Data nyata** | 1.37M rows | Kosong | 46K rows | 4.7K | — | 47 tabel | — | — | — |
| **Frontend** | Next.js ✅ | PHP ❌ | — | — | Streamlit | PHP | PHP | PHP | — |
| **API** | 30+ REST + WS | 14 REST | — | — | — | — | — | — | — |
| **AI/ML** | Linear Reg | Factor model | ARIMA/XGBoost | Labeling+CV | Blueprint | — | LSTM/GRU/Transformer | ML | — |
| **Decision Engine** | ✅ | ✅ (lebih advanced) | — | — | — | — | — | — | — |
| **Risk Engine** | ✅ | ✅ (lebih advanced) | ✅ | — | — | — | — | — | — |
| **Execution** | ✅ Automated | ❌ | ✅ Paper | — | — | — | ✅ Bot | — | — |
| **XAI** | ✅ | ❌ | — | — | ✅ Blueprint | — | — | — | — |
| **Backtest** | ✅ MC + WF | ✅ PIT-safe | — | Walk-fwd | — | — | — | — | SMA |
| **Notifications** | ✅ Telegram | ❌ | ✅ Telegram+Email | — | — | — | — | — | — |
| **Tests** | 235 unit + 4 E2E | 300 (196+104) | — | — | — | — | — | — | — |
| **Docker/CI** | ✅ | ✅ + Prometheus | — | — | — | — | — | — | — |

**Alasan utama memilih `global`:**
1. **Stack modern** — Next.js + FastAPI + SQLite. TIP masih PHP Native MVC (frontend harus rebuild dari nol).
2. **Data nyata** — 1.37M rows OHLCV + 359 watchlist. TIP kosong (schema only, harus import ulang).
3. **Lebih banyak modul** — 18 engines vs TIP ~10. `global` punya AI Learning, XAI, Execution, Paper Trading, Telegram — tidak ada di TIP.
4. **API lebih lengkap** — 30+ endpoints + WebSocket vs TIP 14 endpoints.
5. **Deployment sederhana** — SQLite, tidak butuh Docker/PostgreSQL/TimescaleDB.
6. **Sudah ada Sprint 3** — Parquet archive, module port dari pasar_modal sudah selesai.
7. **CLI lengkap** — 11 commands vs TIP hanya ingest CLI.

### 12.2 Mengapa Bukan TIP sebagai Base

- **Frontend PHP** — harus rebuild dari nol ke Next.js
- **PostgreSQL+TimescaleDB** — infra lebih berat, butuh Docker
- **Tidak ada data** — harus import ulang semua
- **Tidak ada AI Learning/XAI/Execution/Telegram** — harus build dari nol
- **Cost migrasi** jauh lebih tinggi daripada adopt engines TIP ke `global`

### 12.3 TIP sebagai Harta Karun Arsitektural

TIP unggul di **teori quant finance profesional** yang `global` belum punya. 9 engines TIP diadopsi (komponen X–FF di §9):

| TIP Engine | `global` punya? | Nilai adopsi | Komponen §9 |
|-----------|-----------------|-------------|-------------|
| Factor Engine (7 faktor, PIT-safe, cross-sectional rank) | ❌ | **Sangat tinggi** — mengganti weighted scoring dasar | X |
| Alpha Composer (regime multiplier, versioned) | ❌ | **Sangat tinggi** — decision quality upgrade | Y |
| No-Trade Engine (9 gates pre-trade filter) | ❌ | **Sangat tinggi** — risk management | Z |
| Cross-Asset Engine (risk-on/off voting) | ❌ | Tinggi — macro analysis | AA |
| Lead-Lag Analyzer (cross-correlation) | ❌ | Menengah — intelligence layer | BB |
| Data Quality Engine (6 checks) | ❌ | **Sangat tinggi** — data integrity | CC |
| Rate Limiter (circuit breaker) | ❌ | **Sangat tinggi** — reliability | DD |
| Alpha Validation Lab (VALID/WATCH/REJECT) | ❌ | Tinggi — backtest quality | EE |
| Enhanced Risk Engine (vol-targeted, drawdown guard, sector caps) | 🔧 Partial | **Sangat tinggi** — risk upgrade | FF |

### 12.4 Strategi Implementasi

> **`global` = base development. TIP = blueprint arsitektural + source untuk engine upgrades.**

1. **Pertahankan** `global` sebagai base — stack modern, data nyata, lebih lengkap modulnya
2. **Adopsi** 9 engines dari TIP (komponen X–FF di §9) — raw copy untuk yang murni Python, convert DB untuk yang PostgreSQL
3. **Gunakan** `C:\xampp\htdocs\TIP\TRADING_INTELLIGENCE_PLATFORM.md` (4894 baris) sebagai **blueprint arsitektural** untuk evolusi `global`
4. **Import** data dari `data_pasar_modal` (§11, D1–D31) untuk mengisi tabel-tabel kosong di `global`
5. **Adopsi** komponen dari repo lain (A–W) sesuai prioritas di §9.6
6. **Hasil akhir:** `global` + TIP engines + data_pasar_modal data = sistem trading terbaik

### 12.5 Visi Akhir

```
global (base: 18 engines, Next.js, FastAPI, SQLite, 1.37M rows)
  + TIP engines (X–FF: factor model, alpha composer, no-trade, cross-asset, risk)
  + data_pasar_modal data (D1–D31: macro, fundamental, foreign flow, ESG, dll.)
  + swing modules (E, H, I, M, P, Q: paper trading, attribution, manipulation)
  + ML framework (C, D, L, N: purged CV, walk-forward, model registry, labeling)
  + trading-otomatis AI (S, T, U: LSTM/GRU/Transformer, ensemble, order book)
  + belajar_saham (V: trading expectancy)
  + worldmonitor (W: 7-signal composite, CII — referensi arsitektur)
  = Sistem Trading Intelligence terlengkap untuk pasar Indonesia
```

---

## 13. Pre-Implementation Checklist — Yang Harus Diselesaikan Sebelum Implementasi

> **Tanggal:** 1 Agustus 2026
> **Tujuan:** Memastikan dokumen ini akurat dan lengkap sebelum mulai implementasi Sprint 4.

### 13.1 Yang Sudah Diperbaiki di Dokumen Ini (sesi ini)

| # | Item | Status | Catatan |
|---|------|--------|---------|
| 1 | §6 Sprint roadmap tidak mencerminkan STATUS.md | ✅ Diperbaiki | Sprint 1–3 sekarang menampilkan status ✅/❌ per item |
| 2 | §11.4 tidak tahu Parquet archive sudah ada | ✅ Diperbaiki | §11.4a menambahkan info Parquet archive dari Sprint 3 (174 files, 50+ tabel) |
| 3 | §11.4 estimasi usaha terlalu tinggi | ✅ Diperbaiki | Turun dari 2–3 hari → 1–2 hari (Parquet sudah ada) |

### 13.2 Item P2 yang Belum Selesai (dari Sprint 2–3)

Item-item ini **harus diselesaikan sebelum atau bersamaan dengan** adopsi komponen baru, karena menjadi fondasi:

| # | Item | Prioritas | Mengapa harus selesai dulu |
|---|------|-----------|---------------------------|
| **P2-1** | ✅ Integrasi corporate action → `adjusted_close` (§4.3) | ✅ Selesai | Formula split/dividen diperbaiki; acquisition auto-fetch corporate actions; CLI `update-adjusted-close`; 9 tests |
| **P2-2** | ✅ `DataSourceAdapter` multi-sumber + incremental fetch (§4.1) | ✅ Selesai | `SQLiteAdapter`, `CSVAdapter`, `DataSourceManager` dengan priority fallback + auto last_timestamp; 18 tests |
| **P2-3** | ✅ WAL + executemany + Alembic sebagai satu sumber skema (§4.3) | ✅ Selesai | WAL persistent; `executemany_batch()` untuk large imports; 18 tabel D1–D31 di SCHEMA + Alembic `0002`; legacy table migration; 10 tests |
| **P2-4** | ✅ Konsolidasi ATR/fee/slippage ke modul bersama (§4.5) | ✅ Selesai | `risk/costs.py` sebagai single source of truth; 5 modul refactored |
| **P2-5** | ✅ WS broadcast tunggal + cache + pagination (§4.4) | ✅ Selesai | Engine status cache (3s TTL) untuk WS `/ws/live`; pagination di `/api/tickers`, `/api/data/ohlcv`, `/api/watchlist/all`; 7 tests |
| **P2-6** | ✅ Ruff + mypy + coverage gate di CI (§5.1) | ✅ Selesai | Ruff (192→0 errors, 247 auto-fixed), mypy (non-blocking), coverage gate 50% (actual 69%), CI workflow updated |

### 13.3 Dependency Graph — Urutan Adopsi yang Benar

§9.6 membagi adopsi ke 4 fase, tetapi **tidak menunjukkan dependency antar komponen**. Berikut dependency graph yang harus diikuti:

```
Layer 0: Data Foundation (P2-1 ✅, P2-2 ✅, P2-3 ✅) — SELESAI
  │
  ├── P2-1: adjusted_close ─────────────────────────┐
  ├── P2-2: DataSourceAdapter ── A, B, G (scrapers) │
  ├── P2-3: Alembic + WAL ── D1–D31 (data import)   │
  │                                                  │
Layer 1: Data Quality & Reliability — ✅ SELESAI      │
  │                                                  │
  ├── CC: Data Quality Engine ✅ ───────────────┐   │
  ├── DD: Rate Limiter ✅ ──────────────────────│   │
  │                                             │   │
Layer 2: Analysis Engines — ✅ SELESAI            │   │
  │                                             │   │
  ├── K: Advanced Technical ✅ (independent)    │   │
  ├── F: Enhanced Regime ✅ (needs data)        │   │
  ├── X: Factor Engine ✅ ──────────────────────┤   │
  │   └── needs: D2 (instruments), D3 (fund),   │   │
  │       D4 (foreign flow), adjusted_close ────┘   │
  │                                                  │
Layer 3: Signal & Decision — ✅ SELESAI              │
  │                                                  │
  ├── Y: Alpha Composer ✅ ── needs: X (factors), F (regime)
  ├── Z: No-Trade Engine ✅ ── needs: Y (alpha), CC (quality), F (regime)
  │                                                  │
Layer 4: Risk & Validation — ✅ SELESAI               │
  │                                                  │
  ├── FF: Enhanced Risk Engine ✅ ── needs: Y (alpha), P2-4 (ATR konsolidasi) ⏳
  ├── EE: Alpha Validation Lab ✅ ── needs: C (purged CV) ✅, D (walk-forward) ✅
  │                                                  │
Layer 5: Advanced AI — ✅ SELESAI                     │
  │                                                  │
  ├── N: Alpha-Adjusted Labeling ✅ (independent)
  ├── S: Deep Learning ✅ ── needs: N (labels) ✅, C (CV) ✅
  ├── T: Ensemble ✅ ── needs: S ✅ or existing ML
  ├── L: Model Registry ✅ ── needs: S ✅, T ✅
  │                                                  │
Layer 6: Tools & Utilities — ✅ SELESAI (independent) │
  │                                                  │
  ├── C: Purged CV ✅ (independent, raw copy)       │
  ├── D: Walk-Forward ✅ (independent, raw copy)    │
  ├── U: Order Book Analyzer ✅ (independent, raw copy) │
  ├── V: Trading Expectancy ✅ (independent)        │
  ├── P: Email Notification ✅ (independent)        │
  ├── Q: Screener templates ✅ (independent)        │
  ├── AA: Cross-Asset ✅ (needs: D7, D8 global data)│
  ├── BB: Lead-Lag ✅ (needs: ohlcv multi-ticker)   │
  ├── E: Paper Trading ✅ (already in global)       │
  ├── H: Performance Attribution ✅ (independent)   │
  ├── I: Correlation Sizing ✅ (independent)        │
  ├── M: Manipulation Detector ✅ (needs: A, B)     │
  └── W: World Monitor patterns ✅ (independent)    │
```

**Aturan:** Komponen di Layer N tidak boleh diimplementasi sebelum dependency di Layer < N selesai.

### 13.4 Hal Lain yang Perlu Diselesaikan Sebelum Implementasi

| # | Item | Aksi | Mengapa |
|---|------|------|---------|
| **1** | Clone repo GitHub yang belum lokal | ✅ Selesai | `trading-otomatis-indonesia`, `AI_Trading`, `belajar_saham`, `worldmonitor` sudah ada di `C:\xampp\htdocs\` |
| **2** | Analisa `AI_Trading` lebih dalam | ✅ Selesai | Repo hanya berisi README + pyproject.toml — tidak ada folder `src/` atau kode actual. Tidak ada komponen yang bisa diekstrak. |
| **3** | Schema migration plan untuk tabel baru | ✅ Selesai | Alembic `0002_d1_d31_tables.py` + SCHEMA di `storage.py` — 18 tabel D1–D31 dibuat |
| **4** | Mapping Parquet → SQLite schema | ✅ Selesai | `docs/MAPPING_PARQUET_SQLITE.md` — mapping kolom per tabel untuk 18 tabel D1–D31 + OHLCV, transformasi umum, prioritas import |
| **5** | Test plan per komponen | ✅ Selesai | `docs/TEST_PLAN.md` — test plan untuk semua komponen A–FF, 6 layer, 155 test cases |
| **6** | Sinkronisasi taksonomi regime | ✅ Selesai | `macro.py::REGIME_MAP` + `map_regime()` memetakan internal regime → TIP taxonomy (risk_on/risk_off/neutral); `ai_learning/engine.py::REGIME_WEIGHTS` sudah mencakup risk_on/risk_off |
| **7** | `TIP/TRADING_INTELLIGENCE_PLATFORM.md` sebagai blueprint | ✅ Selesai | `docs/TIP_BLUEPRINT_EXTRACTION.md` — ekstraksi arsitektur, schema mapping, regime taxonomy, design patterns |

### 13.5 Rekomendasi Urutan Eksekusi

**Sebelum implementasi komponen apapun:**

1. **Selesaikan P2-1** (adjusted_close) — 1 hari
2. **Selesaikan P2-3** (Alembic + WAL) — 1 hari
3. **Clone 4 repo GitHub** — 30 menit
4. **Buat Alembic migration** untuk tabel baru D1–D31 — 1 hari
5. **Import Parquet → SQLite** (§11.4b) — ✅ Selesai (47,694 rows: OHLCV + instruments + macro + global)
6. **Sinkronisasi taksonomi regime** (§13.4 #6) — setengah hari
7. **Selesaikan P2-2** (DataSourceAdapter) — 1–2 hari

**Setelah itu, baru mulai adopsi komponen sesuai dependency graph (§13.3):**

8. Layer 1: CC (Data Quality) + DD (Rate Limiter) — ✅ Selesai (raw copy, 1 hari)
9. Layer 2: K, F, X — ✅ Selesai (1–2 minggu)
10. Layer 3: Y, Z — ✅ Selesai (1 minggu)
11. Layer 4: FF, EE — ✅ Selesai (1 minggu)
12. Layer 5: N, S, T, L — ✅ Selesai (2–4 minggu)
13. Layer 6: sisanya (independent, bisa paralel) — ✅ Selesai (kecuali U, P, W — tunda)

**Status:** Item 1–13 ✅ SELESAI (562 unit tests passing, 0 warnings, ruff clean, frontend lint clean).

**Komponen yang masih tunda:** Tidak ada — semua komponen U, P, W telah diimplementasi.

---

*Dokumen ini dihasilkan dari analisa statik menyeluruh terhadap kode sumber per 31 Juli 2026, ditambah riset internet terhadap platform sejenis (QuantConnect Lean, NautilusTrader, Freqtrade, Backtrader, vectorbt, Stockbit, RTI Business, IDX Screener, Sectors.app, GoAPI), ditambah eksplorasi menyeluruh per 1 Agustus 2026: 5 repository trading lokal di HDD (pasar_modal, swing, ML, data_pasar_modal, TIP), 4 repository trading di GitHub (trading-otomatis-indonesia, AI_Trading, belajar_saham, worldmonitor), pemeriksaan drive D:\ dan L:\ (tidak ada kode trading), serta inventarisasi database di semua repo (MySQL export, SQLite, CSV, PostgreSQL schema, Parquet archive). Setiap referensi baris merujuk pada kondisi file saat analisa dan dapat bergeser setelah perubahan kode.*
