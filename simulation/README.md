# Simulation & Testing Suite

Folder khusus untuk menjalankan simulasi dan testing terhadap **seluruh fitur** Trading System.

## Struktur

```
simulation/
├── __init__.py      # Package init
├── config.py        # Konfigurasi simulasi (tickers, modal, dll.)
├── run_all.py       # Main orchestrator — jalankan semua modul
├── report.py        # Generator HTML report dari hasil JSON
├── reports/         # Output JSON & HTML (auto-generated)
└── README.md        # Dokumentasi ini
```

## Modul yang Dites

| # | Modul | Fitur yang Disimulasikan |
|---|-------|--------------------------|
| 1 | `data` | Storage, validation, watchlist, list tickers |
| 2 | `analysis` | Pipeline (technical, fundamental, macro, global, relationship) |
| 3 | `decision` | Recommendation engine (BUY/HOLD/SELL, conviction, position sizing) |
| 4 | `risk` | VaR, CVaR, position sizing, transaction costs |
| 5 | `backtest` | 3 strategi (buy_and_hold, ma_crossover, conviction) + Monte Carlo + Walk-Forward |
| 6 | `paper_trading` | Paper trading simulator |
| 7 | `execution` | Mock broker adapter, automated execution engine |
| 8 | `portfolio` | Performance analytics, rebalancer status |
| 9 | `ai_learning` | Linear regression weight optimization, get weights |
| 10 | `xai` | Explainable AI (narrative + top factors) |
| 11 | `monitoring` | System health check |
| 12 | `corporate` | Corporate actions (splits, dividends) |
| 13 | `sentiment` | Sentiment engine (Indonesian NLP) |
| 14 | `api` | 28+ API endpoints via HTTP |
| 15 | `cli` | CLI commands (list, monitor, recommend, explain) |

## Penggunaan

### Jalankan semua modul

```bash
cd /opt/lampp/htdocs/global
python -m simulation.run_all
```

### Pilih modul tertentu

```bash
python -m simulation.run_all --modules data,backtest,decision
```

### Skip modul yang butuh API server

```bash
python -m simulation.run_all --no-api --no-cli
```

### Ganti ticker utama

```bash
python -m simulation.run_all --ticker TLKM.JK
```

### Override parameter via environment variable

```bash
SIM_TICKERS="BBCA.JK,TLKM.JK" SIM_CAPITAL=50000000 SIM_MC_RUNS=1000 python -m simulation.run_all
```

### Generate HTML report

```bash
# Dari JSON terbaru
python -m simulation.report --latest

# Dari file tertentu
python -m simulation.report --file simulation/reports/sim_20250101_120000.json
```

## Prasyarat

- Database SQLite di `data/trading_system.db` dengan data OHLCV
- Python 3.11+ dengan package terinstall (`pip install -e .`)
- Untuk modul `api`: server API berjalan di `localhost:8000`
- Untuk modul `cli`: tidak ada dependency tambahan

## Output

- **JSON**: `simulation/reports/sim_YYYYMMDD_HHMMSS.json` — raw data semua test
- **HTML**: `simulation/reports/sim_YYYYMMDD_HHMMSS.html` — report interaktif dengan summary, module breakdown, dan detailed results table

## Status Test

Setiap test memiliki status:
- **PASS** — test berhasil, fitur berfungsi normal
- **FAIL** — error/exception, fitur tidak berfungsi
- **WARN** — berjalan tapi ada caveat (e.g. data tidak cukup, timeout)
- **SKIP** — tidak bisa dijalankan (e.g. no data, prerequisite tidak terpenuhi)
