$ProgressPreference = 'SilentlyContinue'

function Test-Download {
    param([int64]$Bytes)
    $url = "https://speed.cloudflare.com/__down?bytes=$Bytes"
    $t = Measure-Command { Invoke-WebRequest -Uri $url -OutFile "$env:TEMP\spd.bin" }
    $mbps = ($Bytes * 8) / $t.TotalSeconds / 1MB
    $sizeMB = [math]::Round($Bytes / 1MB, 1)
    Write-Output ("Download {0,5} MB : {1,7:N2} Mbps  ({2:N2}s)" -f $sizeMB, $mbps, $t.TotalSeconds)
    Remove-Item "$env:TEMP\spd.bin" -ErrorAction SilentlyContinue
}

function Test-Upload {
    param([int64]$Bytes)
    $data = New-Object byte[] $Bytes
    (New-Object Random).NextBytes($data)
    $url = "https://speed.cloudflare.com/__up"
    $t = Measure-Command {
        Invoke-WebRequest -Uri $url -Method Post -Body $data -ContentType "application/octet-stream" -OutFile "$env:TEMP\up.txt"
    }
    $mbps = ($Bytes * 8) / $t.TotalSeconds / 1MB
    $sizeMB = [math]::Round($Bytes / 1MB, 1)
    Write-Output ("Upload   {0,5} MB : {1,7:N2} Mbps  ({2:N2}s)" -f $sizeMB, $mbps, $t.TotalSeconds)
    Remove-Item "$env:TEMP\up.txt" -ErrorAction SilentlyContinue
}

# Latency test
$latencies = @()
1..5 | ForEach-Object {
    $t = Measure-Command { try { Invoke-WebRequest -Uri "https://speed.cloudflare.com/__down?bytes=100" -UseBasicParsing -TimeoutSec 5 | Out-Null } catch {} }
    $latencies += $t.TotalMilliseconds
}
$avg = ($latencies | Measure-Object -Average).Average
Write-Output ("Latency  (avg 5) : {0,7:N0} ms" -f $avg)
Write-Output ("-" * 45)

Test-Download -Bytes 10MB
Test-Download -Bytes 50MB
Test-Upload   -Bytes 5MB
