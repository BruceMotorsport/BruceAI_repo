$log = "C:\Users\USER\BruceAI\logs\watchdog_monitor.log"
$envPath = "C:\Users\USER\BruceAI\.env"
$agentLog = "C:\Users\USER\AppData\Local\hermes\profiles\simone\logs\agent.log"
$stateFile = "C:\Users\USER\AppData\Local\Temp\opencode\watch_last_offset.txt"

$key = ""
Select-String -Path $envPath -Pattern '^OPENROUTER_API_KEY=' | ForEach-Object { $key = $_.Line -replace '^OPENROUTER_API_KEY=','' }

$lastOffset = 0
if (Test-Path $stateFile) { $lastOffset = [int64](Get-Content $stateFile -Raw).Trim() }
if ($lastOffset -eq 0 -and (Test-Path $agentLog)) { $lastOffset = (Get-Item $agentLog).Length }

function W($m) { Add-Content -Path $log -Value ("{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m) }

W "monitor started (offset=$lastOffset)"

while ($true) {
    # 1) free pool usage
    try {
        $r = curl.exe -s -m 20 https://openrouter.ai/api/v1/auth/key -H "Authorization: Bearer $key"
        $d = ($r | ConvertFrom-Json).data
        $u = $d.free_model_daily_requests.used
        $lim = $d.free_model_daily_requests.limit
        $rem = $d.free_model_daily_requests.remaining
        W "pool used=$u/$lim remaining=$rem"
        if ($rem -lt 100) { W "WARNING: free pool low ($rem left)" }
        if ($rem -le 0) { W "ALERT: free pool exhausted - simone will fall back to groq" }
    } catch { W "pool check failed: $($_.Exception.Message)" }

    # 2) services
    $c = Test-NetConnection -ComputerName 127.0.0.1 -Port 9001 -WarningAction SilentlyContinue -InformationLevel Quiet
    $b = Test-NetConnection -ComputerName 127.0.0.1 -Port 8080 -WarningAction SilentlyContinue -InformationLevel Quiet
    if (-not $c) { W "ALERT: console :9001 DOWN" }
    if (-not $b) { W "ALERT: bridge :8080 DOWN" }

    # 3) new errors in agent.log
    if (Test-Path $agentLog) {
        $len = (Get-Item $agentLog).Length
        if ($len -gt $lastOffset) {
            $fs = [System.IO.File]::Open($agentLog, 'Open', 'Read', 'ReadWrite')
            $fs.Seek($lastOffset, 'Begin') | Out-Null
            $sr = New-Object System.IO.StreamReader($fs)
            $new = $sr.ReadToEnd()
            $sr.Close(); $fs.Close()
            $lastOffset = $len
            Set-Content -Path $stateFile -Value $lastOffset
            foreach ($line in ($new -split "`n")) {
                if ($line -match 'ERROR|error_type=|402|too large|ALERT') {
                    W ("agent: " + $line.Trim().Substring(0, [Math]::Min(240, $line.Trim().Length)))
                }
                if ($line -match 'Turn ended') {
                    W ("turn: " + $line.Trim().Substring(0, [Math]::Min(240, $line.Trim().Length)))
                }
            }
        }
    }
    Start-Sleep -Seconds 300
}
