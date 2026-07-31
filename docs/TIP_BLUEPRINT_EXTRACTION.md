# TIP Blueprint Extraction (§13.4 #7)

> Ekstrak blueprint arsitektur dari `TIP/TRADING_INTELLIGENCE_PLATFORM.md` (4894 baris)
> untuk adaptasi ke sistem `global` berbasis SQLite.

---

## 1. Arsitektur Inti TIP

```
Data → Analisis → Sinyal → Keputusan → Eksekusi → Monitoring → Evaluasi
                                                        │
                                                        ▼
                                                  FEEDBACK LOOP
```

### Layer TIP → Adaptasi Global

| TIP Layer | TIP Tech | Global Adaptasi | Status |
|---|---|---|---|
| Data Ingestion | PostgreSQL + TimescaleDB | SQLite + Parquet archive | ✅ Done |
| Data Quality | `quality.py` (pandas) | Merge ke `validation.py` | Layer 1 |
| Factor Engine | `factor_engine.py` (PostgreSQL) | Adaptasi ke SQLite `DataStorage` | Layer 2 |
| Regime Engine | `global_regime.py` + `indonesia_regime.py` | Merge ke `macro.py` | Layer 2 |
| Alpha Composer | `alpha_composer.py` (pure dataclass) | Raw copy, adapt regime taxonomy | Layer 3 |
| No-Trade Engine | `no_trade.py` (pure dataclass) | Raw copy | Layer 3 |
| Risk Engine | `risk_engine.py` (pure Python) | Replace `risk/engine.py` | Layer 4 |
| Alpha Validation | `alpha_validation.py` (pure numpy) | Raw copy | Layer 4 |
| Rate Limiter | `rate_limit.py` (circuit breaker) | Replace simple `RateLimiter` | Layer 1 |

## 2. Database Schema Mapping

| TIP (PostgreSQL) | Global (SQLite) | Catatan |
|---|---|---|
| `tip.instruments` | `instrument_master` | D1 import |
| `tip.market_bars` | `ohlcv` | Existing, +adjusted_close |
| `tip.fundamentals` | `fundamental_data` | D3 import |
| `tip.corporate_actions` | `corporate_actions` + `corporate_actions_legacy` | Existing + D10 |
| `tip.macro_series` | `macro_data` | D1 import |
| `tip.sectors` | `sector_master` | D12 import |

## 3. Regime Taxonomy Mapping

| TIP Regime | Global Internal | Global `map_regime()` |
|---|---|---|
| `bull` | `growth` / `easing` | `risk_on` |
| `risk_on` | `growth` / `easing` | `risk_on` |
| `neutral` | `neutral` | `neutral` |
| `sideways` | `neutral` | `neutral` |
| `bear` | `tightening` / `slowdown` | `risk_off` |
| `risk_off` | `tightening` / `slowdown` | `risk_off` |
| `crisis` | `unknown` | `neutral` (gate to 0.0) |
| `unknown` | `unknown` | `neutral` (gate to 0.0) |

## 4. Komponen TIP yang TIDAK Diadopsi

- PostgreSQL/TimescaleDB — tetap SQLite
- Microservice architecture (17 services) — tetap monolith modular
- Broker API/DMA Gateway — tidak ada broker API untuk IDX retail
- Short selling / hedging engine — terbatas di IDX
- Tick data / order book — tidak tersedia untuk IDX gratis

## 5. Key Design Patterns dari TIP

1. **Versioned outputs** — setiap engine menyertakan `version` string di output
2. **Reason codes** — setiap keputusan disertai list alasan untuk audit
3. **Config dataclasses** — setiap engine punya `@dataclass Config` untuk parameter
4. **PIT-safe** — semua komputasi hanya menggunakan data sampai `as_of`
5. **Cross-sectional ranking** — percentile rank untuk factor scoring
6. **Gate-based decisions** — No-Trade engine menggunakan multiple gates
7. **Circuit breaker** — rate limiter dengan open/half-open/closed states
