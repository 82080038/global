"""Speed test ke sumber data aktual (Yahoo Finance + IDX)."""
import time
import urllib.request
import urllib.error
import statistics
import json

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


def fetch(url, timeout=15):
    """Return (status_code, bytes_count, elapsed_sec) or (None, 0, elapsed) on error."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
            return r.status, len(data), time.perf_counter() - t0
    except urllib.error.HTTPError as e:
        return e.code, 0, time.perf_counter() - t0
    except Exception:
        return None, 0, time.perf_counter() - t0


def test_latency(name, url, hits=5):
    lats, ok, last_status = [], 0, None
    for _ in range(hits):
        status, _, elapsed = fetch(url)
        if status == 200:
            ok += 1
            lats.append(elapsed * 1000)
        else:
            lats.append(15000)
        last_status = status
    avg, mn, mx = statistics.mean(lats), min(lats), max(lats)
    print(f"{name:<32} avg={avg:>7.0f}ms  min={mn:>7.0f}ms  max={mx:>7.0f}ms  ok={ok}/{hits}  HTTP={last_status}")
    return ok, avg


def test_throughput(name, url):
    status, nbytes, elapsed = fetch(url, timeout=30)
    if status != 200:
        print(f"{name:<32} FAILED (HTTP={status})")
        return
    mbps = (nbytes * 8) / elapsed / 1_000_000
    print(f"{name:<32} size={nbytes/1024:>7.1f}KB  time={elapsed:.2f}s  speed={mbps:.2f} Mbps")


def test_bulk(tickers, range_str="1mo"):
    ok, total = 0, 0.0
    for tk in tickers:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{tk}?interval=1d&range={range_str}"
        status, _, elapsed = fetch(url, timeout=15)
        total += elapsed
        if status == 200:
            ok += 1
    per_req = total / len(tickers) * 1000
    print(f"{len(tickers)} tickers .JK: {ok}/{len(tickers)} OK  {total:.2f}s total  ({per_req:.0f}ms/request)")
    return per_req


print("=" * 70)
print("LATENCY ke sumber data aktual (User-Agent browser, 5 hit each)")
print("=" * 70)
test_latency("Yahoo BBCA.JK (5d)", "https://query1.finance.yahoo.com/v8/finance/chart/BBCA.JK?interval=1d&range=5d")
test_latency("Yahoo AAPL (5d)",    "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?interval=1d&range=5d")
test_latency("Yahoo TLKM.JK (5d)", "https://query1.finance.yahoo.com/v8/finance/chart/TLKM.JK?interval=1d&range=5d")
test_latency("Yahoo ^JKSE (5d)",   "https://query1.finance.yahoo.com/v8/finance/chart/%5EJKSE?interval=1d&range=5d")
test_latency("IDX ListedCompany",  "https://www.idx.co.id/primary/ListedCompany")
test_latency("IDX homepage",       "https://www.idx.co.id/en-us/market-data/stocks-data/listed-companies/")

print()
print("=" * 70)
print("THROUGHPUT download (1y history)")
print("=" * 70)
test_throughput("Yahoo BBCA.JK (1y)", "https://query1.finance.yahoo.com/v8/finance/chart/BBCA.JK?interval=1d&range=1y")
test_throughput("Yahoo ^JKSE (1y)",   "https://query1.finance.yahoo.com/v8/finance/chart/%5EJKSE?interval=1d&range=1y")

print()
print("=" * 70)
print("BULK FETCH sequential (estimasi untuk 989 ticker)")
print("=" * 70)
t5 = ["BBCA.JK", "TLKM.JK", "ASII.JK", "UNVR.JK", "BMRI.JK"]
t10 = t5 + ["BBRI.JK", "GOTO.JK", "ANTM.JK", "PGAS.JK", "INDF.JK"]
p5 = test_bulk(t5)
p10 = test_bulk(t10)

est_no_rl = p10 / 1000 * 989
est_with_rl = est_no_rl + 989 * 1.5
print()
print(f"Estimasi 989 ticker (tanpa rate-limit sleep): {est_no_rl/60:.1f} menit")
print(f"Estimasi 989 ticker (dengan rate-limit 1.5s): {est_with_rl/60:.1f} menit")
