"""Verify IDX.co.id access via the same bypass methods used by the codebase."""
import time
import statistics

URL = "https://www.idx.co.id/primary/TradingSummary/getStockSummary?date=20260731"
HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.idx.co.id/id/data-pasar/ringkasan-perdagangan/ringkasan-saham/",
}


def test_cloudscraper(hits=5):
    import cloudscraper
    s = cloudscraper.create_scraper()
    lats, ok, last = [], 0, None
    for _ in range(hits):
        t0 = time.perf_counter()
        try:
            r = s.get(URL, headers=HEADERS, timeout=20)
            last = r.status_code
            if r.status_code == 200:
                ok += 1
                lats.append((time.perf_counter() - t0) * 1000)
            else:
                lats.append(20000)
        except Exception as e:
            last = f"ERR: {type(e).__name__}"
            lats.append(20000)
    avg = statistics.mean(lats) if lats else 0
    print(f"cloudscraper   avg={avg:>7.0f}ms  ok={ok}/{hits}  last={last}")
    return ok, avg


def test_curl_cffi(hits=5):
    from curl_cffi import requests as cffi
    lats, ok, last = [], 0, None
    for _ in range(hits):
        t0 = time.perf_counter()
        try:
            r = cffi.get(URL, headers=HEADERS, timeout=20, impersonate="chrome")
            last = r.status_code
            if r.status_code == 200:
                ok += 1
                lats.append((time.perf_counter() - t0) * 1000)
            else:
                lats.append(20000)
        except Exception as e:
            last = f"ERR: {type(e).__name__}"
            lats.append(20000)
    avg = statistics.mean(lats) if lats else 0
    print(f"curl_cffi      avg={avg:>7.0f}ms  ok={ok}/{hits}  last={last}")
    return ok, avg


print("=" * 60)
print("IDX.co.id access test (bypass Cloudflare via codebase methods)")
print(f"URL: {URL}")
print("=" * 60)
print()
print("[1] cloudscraper (idx_scraper.py)")
cs_ok, cs_avg = test_cloudscraper()
print()
print("[2] curl_cffi impersonate=chrome (idx_batch.py)")
cc_ok, cc_avg = test_curl_cffi()

print()
print("=" * 60)
print("KESIMPULAN")
print("=" * 60)
if cs_ok > 0 or cc_ok > 0:
    print("IDX.co.id: AKSES BERHASIL via bypass library")
    print(f"  cloudscraper: {cs_ok}/5 OK ({cs_avg:.0f}ms avg)")
    print(f"  curl_cffi:    {cc_ok}/5 OK ({cc_avg:.0f}ms avg)")
    print()
    print("Catatan: tes sebelumnya pakai urllib biasa -> 403 (tanpa bypass)")
    print("Scraper asli di codebase TIDAK terkena blokir -> WiFi baru OK")
else:
    print("IDX.co.id: GAGAL via bypass library juga")
    print("-> kemungkinan masalah di sisi IDX atau IP diblokir")
