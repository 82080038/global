$ProgressPreference = 'SilentlyContinue'

$headers = @{
    'User-Agent' = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
}

function Test-Endpoint {
    param([string]$Name, [string]$Url, [int]$Hits = 5)
    $latencies = @()
    $ok = 0
    $lastStatus = 0
    1..$Hits | ForEach-Object {
        try {
            $t = Measure-Command {
                $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 15 -Headers $headers
                $script:lastStatus = $r.StatusCode
                if ($r.StatusCode -eq 200) { $script:ok++ }
            }
            $latencies += $t.TotalMilliseconds
        } catch {
            $latencies += 15000
            $script:lastStatus = $_.Exception.Response.StatusCode.value__
        }
    }
    $avg = ($latencies | Measure-Object -Average).Average
    $min = ($latencies | Measure-Object -Minimum).Minimum
    $max = ($latencies | Measure-Object -Maximum).Maximum
    Write-Output ("{0,-32} avg={1,7:N0}ms  min={2,7:N0}ms  max={3,7:N0}ms  ok={4}/{5}  HTTP={6}" -f $Name, $avg, $min, $max, $ok, $Hits, $lastStatus)
}

Write-Output "=== Latency ke sumber data aktual (User-Agent browser, 5 hit each) ==="
Write-Output ""
Test-Endpoint -Name "Yahoo BBCA.JK (5d)"   -Url "https://query1.finance.yahoo.com/v8/finance/chart/BBCA.JK?interval=1d&range=5d"
Test-Endpoint -Name "Yahoo AAPL (5d)"      -Url "https://query1.finance.yahoo.com/v8/finance/chart/AAPL?interval=1d&range=5d"
Test-Endpoint -Name "Yahoo TLKM.JK (5d)"   -Url "https://query1.finance.yahoo.com/v8/finance/chart/TLKM.JK?interval=1d&range=5d"
Test-Endpoint -Name "IDX ListedCompany"    -Url "https://www.idx.co.id/primary/ListedCompany"
Test-Endpoint -Name "IDX SSE (homepage)"   -Url "https://www.idx.co.id/en-us/market-data/stocks-data/listed-companies/"

Write-Output ""
Write-Output "=== Throughput: 1y history BBCA.JK ==="
$url = "https://query1.finance.yahoo.com/v8/finance/chart/BBCA.JK?interval=1d&range=1y"
$t = Measure-Command {
    $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 30 -Headers $headers
    $script:bytes = $r.RawContentLength
}
$mbps = ($bytes * 8) / $t.TotalSeconds / 1MB
Write-Output ("Size: {0:N1} KB   Time: {1:N2}s   Speed: {2:N2} Mbps" -f ($bytes/1KB), $t.TotalSeconds, $mbps)

Write-Output ""
Write-Output "=== Bulk fetch 5 ticker .JK sequential (1mo range) ==="
$tickers = @("BBCA.JK","TLKM.JK","ASII.JK","UNVR.JK","BMRI.JK")
$okCount = 0
$tTotal = Measure-Command {
    foreach ($tk in $tickers) {
        try {
            $r = Invoke-WebRequest -Uri "https://query1.finance.yahoo.com/v8/finance/chart/$tk?interval=1d&range=1mo" -UseBasicParsing -TimeoutSec 15 -Headers $headers
            if ($r.StatusCode -eq 200) { $okCount++ }
        } catch {}
    }
}
$perReq = $tTotal.TotalSeconds / $tickers.Count
Write-Output ("5 tickers .JK: {0}/{1} OK   {2:N2}s total   ({3:N0}ms / request)" -f $okCount, $tickers.Count, $tTotal.TotalSeconds, $perReq*1000)

Write-Output ""
Write-Output "=== Bulk fetch 10 ticker .JK sequential (estimasi untuk 989 ticker) ==="
$tickers10 = @("BBCA.JK","TLKM.JK","ASII.JK","UNVR.JK","BMRI.JK","BBRI.JK","GOTO.JK","ANTM.JK","PGAS.JK","INDF.JK")
$okCount10 = 0
$tTotal10 = Measure-Command {
    foreach ($tk in $tickers10) {
        try {
            $r = Invoke-WebRequest -Uri "https://query1.finance.yahoo.com/v8/finance/chart/$tk?interval=1d&range=1mo" -UseBasicParsing -TimeoutSec 15 -Headers $headers
            if ($r.StatusCode -eq 200) { $okCount10++ }
        } catch {}
    }
}
$perReq10 = $tTotal10.TotalSeconds / $tickers10.Count
$est989 = $perReq10 * 989
Write-Output ("10 tickers .JK: {0}/{1} OK   {2:N2}s total   ({3:N0}ms / request)" -f $okCount10, $tickers10.Count, $tTotal10.TotalSeconds, $perReq10*1000)
Write-Output ("Estimasi 989 ticker (tanpa rate-limit sleep): {0:N1} menit" -f ($est989/60))
Write-Output ("Estimasi 989 ticker (dengan rate-limit 1.5s): {1:N1} menit" -f $est989, ($est989 + 989*1.5)/60)
