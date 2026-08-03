"""Stress test to find optimal rate-limit for Yahoo Finance and IDX.

Strategy: send N requests at each candidate delay, record success rate.
Optimal = lowest delay with 100% success, then apply 50% safety margin.
"""
import time
import statistics
import urllib.request
import urllib.error

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

YF_TICKERS = [
    "BBCA.JK", "TLKM.JK", "ASII.JK", "UNVR.JK", "BMRI.JK",
    "BBRI.JK", "GOTO.JK", "ANTM.JK", "PGAS.JK", "INDF.JK",
    "ICBP.JK", "SMGR.JK", "KLBF.JK", "ADRO.JK", "CPIN.JK",
    "CTRA.JK", "BSDE.JK", "LPKR.JK", "MDKA.JK", "MEDC.JK",
    "AKRA.JK", "EMTK.JK", "EXCL.JK", "ISAT.JK", "MYOR.JK",
    "PNLF.JK", "PTBA.JK", "TINS.JK", "TOTL.JK", "TOWR.JK",
]

IDX_DATES = [
    "20260731", "20260730", "20260729", "20260728", "20260725",
    "20260724", "20260723", "20260722", "20260721", "20260718",
    "20260717", "20260716", "20260715", "20260714", "20260711",
    "20260710", "20260709", "20260708", "20260707", "20260704",
    "20260703", "20260702", "20260701", "20260630", "20260627",
    "20260626", "20260625", "20260624", "20260623", "20260620",
]


def fetch_yf(ticker, timeout=15):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read()
            return r.status, time.perf_counter() - t0
    except urllib.error.HTTPError as e:
        return e.code, time.perf_counter() - t0
    except Exception:
        return None, time.perf_counter() - t0


def fetch_idx(date_str, scraper, timeout=15):
    url = f"https://www.idx.co.id/primary/TradingSummary/getStockSummary?date={date_str}"
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.idx.co.id/id/data-pasar/ringkasan-perdagangan/ringkasan-saham/",
    }
    t0 = time.perf_counter()
    try:
        r = scraper.get(url, headers=headers, timeout=timeout)
        return r.status_code, time.perf_counter() - t0
    except Exception:
        return None, time.perf_counter() - t0


def stress_test_yf(delays, n=30):
    print("\n" + "=" * 70)
    print("YAHOO FINANCE stress test (30 requests per delay level)")
    print("=" * 70)
    results = {}
    for delay in delays:
        ok, fail, codes, lats = 0, 0, {}, []
        for i in range(n):
            ticker = YF_TICKERS[i % len(YF_TICKERS)]
            status, elapsed = fetch_yf(ticker)
            lats.append(elapsed * 1000)
            if status == 200:
                ok += 1
            else:
                fail += 1
                codes[status] = codes.get(status, 0) + 1
            if delay > 0:
                time.sleep(delay)
        avg_lat = statistics.mean(lats)
        results[delay] = {"ok": ok, "fail": fail, "codes": codes, "avg_lat": avg_lat}
        status_str = f"OK={ok}/{n}" + (f"  FAIL codes={codes}" if codes else "")
        print(f"  delay={delay:.2f}s  {status_str}  avg_lat={avg_lat:.0f}ms  total_time={sum(lats)/1000 + delay*n:.1f}s")
    return results


def stress_test_idx(delays, n=20):
    print("\n" + "=" * 70)
    print("IDX.co.id stress test via curl_cffi (20 requests per delay level)")
    print("=" * 70)
    from curl_cffi import requests as cffi
    results = {}
    for delay in delays:
        ok, fail, codes, lats = 0, 0, {}, []
        for i in range(n):
            date_str = IDX_DATES[i % len(IDX_DATES)]
            url = f"https://www.idx.co.id/primary/TradingSummary/getStockSummary?date={date_str}"
            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://www.idx.co.id/id/data-pasar/ringkasan-perdagangan/ringkasan-saham/",
            }
            t0 = time.perf_counter()
            try:
                r = cffi.get(url, headers=headers, timeout=15, impersonate="chrome")
                status = r.status_code
                elapsed = time.perf_counter() - t0
                if status == 200:
                    ok += 1
                else:
                    fail += 1
                    codes[status] = codes.get(status, 0) + 1
            except Exception as e:
                elapsed = time.perf_counter() - t0
                fail += 1
                codes[f"ERR:{type(e).__name__}"] = 1
            lats.append(elapsed * 1000)
            if delay > 0:
                time.sleep(delay)
        avg_lat = statistics.mean(lats)
        results[delay] = {"ok": ok, "fail": fail, "codes": codes, "avg_lat": avg_lat}
        status_str = f"OK={ok}/{n}" + (f"  FAIL codes={codes}" if codes else "")
        print(f"  delay={delay:.2f}s  {status_str}  avg_lat={avg_lat:.0f}ms  total_time={sum(lats)/1000 + delay*n:.1f}s")
    return results


def calculate_optimal(results, label, n_tickers=989):
    print(f"\n--- Optimal rate-limit calculation: {label} ---")
    # Find lowest delay with 100% success
    best_delay = None
    for delay in sorted(results.keys()):
        r = results[delay]
        if r["fail"] == 0:
            best_delay = delay
            break
    if best_delay is None:
        # Find lowest delay with >=95% success
        for delay in sorted(results.keys()):
            r = results[delay]
            if r["ok"] / (r["ok"] + r["fail"]) >= 0.95:
                best_delay = delay
                break
    if best_delay is None:
        print(f"  WARNING: No delay achieved >=95% success. Using highest tested.")
        best_delay = max(results.keys())

    # Apply 50% safety margin
    optimal = best_delay * 1.5
    # Round to nice value
    if optimal < 0.2:
        optimal_rounded = 0.2
    elif optimal < 0.5:
        optimal_rounded = round(optimal * 10) / 10
    else:
        optimal_rounded = round(optimal * 2) / 2  # round to 0.5

    print(f"  Lowest delay with 100% success: {best_delay:.2f}s")
    print(f"  With 50% safety margin:         {optimal:.2f}s")
    print(f"  Recommended (rounded):          {optimal_rounded:.2f}s")
    print(f"  Estimasi 989 ticker:            {optimal_rounded * 989 / 60:.1f} menit")
    return optimal_rounded


# Run tests
print("Starting stress test...")
print(f"Network: current WiFi")

yf_results = stress_test_yf([0.0, 0.1, 0.2, 0.3, 0.5], n=30)
yf_optimal = calculate_optimal(yf_results, "Yahoo Finance")

idx_results = stress_test_idx([0.0, 0.1, 0.2, 0.3, 0.5], n=20)
idx_optimal = calculate_optimal(idx_results, "IDX.co.id")

print("\n" + "=" * 70)
print("FINAL RECOMMENDATION")
print("=" * 70)
print(f"  YFINANCE_DELAY = {yf_optimal:.2f}s   (current: 0.50s)")
print(f"  IDX_DELAY      = {idx_optimal:.2f}s   (current: 0.30s)")
print(f"  RSS_DELAY      = 1.0s    (keep — RSS feeds are polite-only)")
print()
print(f"  Estimasi 989 ticker Yahoo: {yf_optimal * 989 / 60:.1f} menit")
print(f"  Estimasi 20 IDX dates:     {idx_optimal * 20 / 60:.1f} menit")
