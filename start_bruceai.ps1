#Requires -Version 5.1
<#
.SYNOPSIS
    BruceAI service manager: Groq Bridge (:8080) + Provider Console (:9001).

.DESCRIPTION
    Actions:
      Start        Kill anything on the ports, launch both services detached, health-check them.
      Stop         Stop the supervisor (if any) then kill both services.
      Restart      Stop + Start.
      Status       Show supervisor, port owners, health JSON and key sources.
      Supervise    Start, then stay resident and repair the services if they die (used by Task Scheduler).
      InstallTask  Register the "BruceAI Services" scheduled task (auto-start at logon/boot).
      UninstallTask Remove that scheduled task.

    Keys are read from .\.env only. A placeholder/empty value falls back to a real key found in
    the local Hermes profile .env files. Nothing is ever hardcoded or printed.

.EXAMPLE
    .\start_bruceai.ps1 Start -SmokeTest
    .\start_bruceai.ps1 InstallTask
    .\start_bruceai.ps1 Status
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('Start', 'Stop', 'Restart', 'Status', 'InstallTask', 'UninstallTask', 'Supervise', 'Prune')]
    [string]$Action = 'Start',

    [int]$BridgePort = 8080,
    [int]$ConsolePort = 9001,
    [int]$StartupTimeoutSec = 60,
    [int]$MonitorIntervalSec = 20,
    [string]$TaskName = 'BruceAI Services',
    [switch]$SmokeTest,
    [switch]$NoHealthCheck
)

$ErrorActionPreference = 'Stop'

# ─── PATHS ───────────────────────────────────────────────────────────────
$script:Root = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$script:BridgeScript  = Join-Path $script:Root 'groq_bridge.py'
$script:ConsoleScript = Join-Path $script:Root 'main.py'
$script:EnvFile       = Join-Path $script:Root '.env'
$script:LogDir        = Join-Path $script:Root 'logs'
$script:LogFile       = Join-Path $script:LogDir ('bruceai_{0}.log' -f (Get-Date -Format 'yyyyMMdd'))
$script:BridgeUrl     = 'http://127.0.0.1:{0}' -f $BridgePort
$script:ConsoleUrl    = 'http://127.0.0.1:{0}' -f $ConsolePort
$script:PidFile       = Join-Path (Join-Path $script:Root 'logs') 'supervisor.pid'

$script:BridgePid  = $null
$script:ConsolePid = $null

if (-not (Test-Path -LiteralPath $script:LogDir)) {
    New-Item -ItemType Directory -Path $script:LogDir -Force | Out-Null
}

# ─── LOGGING ─────────────────────────────────────────────────────────────
function Write-Log {
    param([string]$Message, [string]$Level = 'INFO')
    $line = '{0} [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    switch ($Level) {
        'ERROR' { Write-Host $line -ForegroundColor Red }
        'WARN'  { Write-Host $line -ForegroundColor Yellow }
        'OK'    { Write-Host $line -ForegroundColor Green }
        default { Write-Host $line }
    }
    try { Add-Content -LiteralPath $script:LogFile -Value $line -Encoding UTF8 } catch { }
}

# ─── .ENV HANDLING ───────────────────────────────────────────────────────
function Read-EnvFile {
    param([string]$Path)
    $map = @{}
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path)) { return $map }
    foreach ($line in (Get-Content -LiteralPath $Path -ErrorAction Stop)) {
        $t = $line.Trim()
        if ($t -eq '' -or $t.StartsWith('#')) { continue }
        $idx = $t.IndexOf('=')
        if ($idx -lt 1) { continue }
        $key = $t.Substring(0, $idx).Trim()
        $val = $t.Substring($idx + 1).Trim()
        if ($val.Length -ge 2) {
            $a = $val[0]; $b = $val[$val.Length - 1]
            if (($a -eq '"' -and $b -eq '"') -or ($a -eq "'" -and $b -eq "'")) { $val = $val.Substring(1, $val.Length - 2) }
        }
        $map[$key] = $val
    }
    return $map
}

function Test-RealKey {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return $false }
    if ($Value -match '<|>|\bYOUR_|\byour_|\bchangeme\b|placeholder|dummy|test_key|^xxx+$') { return $false }
    if ($Value.Length -lt 12) { return $false }
    return $true
}

function Get-EnvKeySources {
    <# Resolves the API keys. BruceAI\.env wins; placeholders fall back to the real keys that
       already exist locally in the Hermes profile .env files. Returns a hashtable of resolved
       values plus a per-key source label (never the value itself). #>
    $resolved = @{}
    $sources  = @{}

    $primary = Read-EnvFile -Path $script:EnvFile
    foreach ($k in $primary.Keys) { $resolved[$k] = $primary[$k] }
    foreach ($k in $primary.Keys) { $sources[$k] = '.env' }

    $keysToSource = @('GROQ_API_KEY', 'OPENROUTER_API_KEY', 'OPENCODE_API_KEY', 'BRUCEAI_API_KEY')
    $fallbacks = @()
    $hermesRoot = Join-Path $env:LOCALAPPDATA 'hermes'
    if (Test-Path -LiteralPath (Join-Path $hermesRoot 'profiles')) {
        foreach ($p in (Get-ChildItem -LiteralPath (Join-Path $hermesRoot 'profiles') -Directory -ErrorAction SilentlyContinue)) {
            $fallbacks += (Join-Path $p.FullName '.env')
        }
    }
    $fallbacks += (Join-Path $hermesRoot '.env')

    foreach ($k in $keysToSource) {
        if (Test-RealKey -Value $resolved[$k]) { continue }
        foreach ($file in $fallbacks) {
            $map = Read-EnvFile -Path $file
            if ((Test-RealKey -Value $map[$k])) {
                $resolved[$k] = $map[$k]
                $rel = $file.Substring($env:LOCALAPPDATA.Length + 1)
                $sources[$k] = 'fallback: ' + $rel
                break
            }
        }
    }
    return @{ Values = $resolved; Sources = $sources }
}

function Set-ProcessEnv {
    param([hashtable]$Map)
    $sensitive = @('GROQ_API_KEY', 'OPENROUTER_API_KEY', 'OPENCODE_API_KEY', 'OPENCODE_KEY', 'BRUCEAI_API_KEY')
    foreach ($k in $Map.Keys) {
        # Never export a placeholder: services must report "not configured" honestly.
        if ($sensitive -contains $k -and -not (Test-RealKey -Value $Map[$k])) { continue }
        [Environment]::SetEnvironmentVariable($k, [string]$Map[$k], 'Process')
    }
    # main.py reads OPENCODE_KEY; the .env file names it OPENCODE_API_KEY (the name the
    # opencode subprocess and Hermes ${...} reference use). Expose both.
    if ($Map.ContainsKey('OPENCODE_API_KEY') -and -not $Map.ContainsKey('OPENCODE_KEY')) {
        [Environment]::SetEnvironmentVariable('OPENCODE_KEY', [string]$Map['OPENCODE_API_KEY'], 'Process')
    }
    if (-not $Map.ContainsKey('GROQ_BRIDGE_URL')) {
        [Environment]::SetEnvironmentVariable('GROQ_BRIDGE_URL', "$script:BridgeUrl/v1", 'Process')
    }
    [Environment]::SetEnvironmentVariable('PORT', [string]$ConsolePort, 'Process')
}

function Report-KeySources {
    param([hashtable]$Sources, [hashtable]$Values)
    foreach ($k in @('GROQ_API_KEY', 'OPENROUTER_API_KEY', 'OPENCODE_API_KEY', 'BRUCEAI_API_KEY')) {
        $src  = $Sources[$k]
        $val  = $Values[$k]
        if (-not $src) { Write-Log "$k : not present anywhere" 'WARN'; continue }
        if (Test-RealKey -Value $val) {
            $tail = $val.Substring($val.Length - 4)
            Write-Log ("{0} : from {1} (len {2}, ****{3})" -f $k, $src, $val.Length, $tail)
        } else {
            Write-Log "$k : PLACEHOLDER in $src - feature will be unavailable until a real key is set" 'WARN'
        }
    }
}

# ─── PYTHON ──────────────────────────────────────────────────────────────
function Resolve-Python {
    if ($env:BRUCEAI_PYTHON -and (Test-Path -LiteralPath $env:BRUCEAI_PYTHON)) {
        return @{ Path = $env:BRUCEAI_PYTHON; Prefix = @() }
    }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python310\python.exe'),
        (Join-Path $env:ProgramFiles 'Python311\python.exe'),
        (Join-Path $env:ProgramFiles 'Python312\python.exe')
    )
    foreach ($c in $candidates) { if (Test-Path -LiteralPath $c) { return @{ Path = $c; Prefix = @() } } }
    $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($cmd) { return @{ Path = $cmd.Source; Prefix = @() } }
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) { return @{ Path = $py.Source; Prefix = @('-3') } }
    throw 'Python not found. Install Python 3.11+ or set BRUCEAI_PYTHON.'
}

function Test-PythonDeps {
    param([hashtable]$Python)
    $pyArgs = @($Python.Prefix) + @('-c', 'import fastapi, uvicorn, httpx, pydantic')
    $out = & $Python.Path @pyArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Python dependencies missing ($($out -join ' ')). Run: python -m pip install fastapi uvicorn httpx pydantic"
    }
}

# ─── PORT / PROCESS CONTROL ──────────────────────────────────────────────
function Get-PortOwners {
    param([int]$Port)
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) { return @() }
    return @($conns | Select-Object -ExpandProperty OwningProcess -Unique)
}

function Stop-PortOwners {
    param([int]$Port, [int]$TimeoutSec = 20)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    do {
        $owners = Get-PortOwners -Port $Port
        if ($owners.Count -eq 0) { return $true }
        foreach ($procId in $owners) {
            if ($procId -eq $PID) { continue }
            $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
            if (-not $p) { continue }
            try {
                Write-Log "Port $Port held by $($p.ProcessName) (PID $procId) - stopping it"
                Stop-Process -Id $procId -Force -ErrorAction Stop
            } catch {
                Write-Log "Could not stop PID $procId on port $Port : $($_.Exception.Message)" 'WARN'
            }
        }
        Start-Sleep -Milliseconds 600
    } while ((Get-Date) -lt $deadline)

    $left = Get-PortOwners -Port $Port
    if ($left.Count -gt 0) {
        Write-Log "Port $Port still occupied by PID(s) $($left -join ', ') after ${TimeoutSec}s" 'ERROR'
        return $false
    }
    return $true
}

function Get-SupervisorPids {
    <# Live supervisor PID(s) recorded in the PID file. Scanning process command lines gives
       false positives (any shell that merely typed the launch command matches), so the PID file
       is the source of truth and the recorded process is only verified, never guessed. #>
    $found = @()
    if (-not (Test-Path -LiteralPath $script:PidFile)) { return $found }
    foreach ($line in (Get-Content -LiteralPath $script:PidFile -ErrorAction SilentlyContinue)) {
        $procId = 0
        if (-not [int]::TryParse(([string]$line).Trim(), [ref]$procId)) { continue }
        if ($procId -eq $PID) { continue }
        if (-not (Get-Process -Id $procId -ErrorAction SilentlyContinue)) { continue }
        try {
            $p = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction Stop
            $cl = [string]$p.CommandLine
            if ($cl -match 'start_bruceai\.ps1' -and $cl -match 'Supervise') { $found += $procId }
        } catch { }
    }
    return $found
}

function Stop-Supervisors {
    foreach ($procId in (Get-SupervisorPids)) {
        try {
            Write-Log "Stopping supervisor PID $procId"
            Stop-Process -Id $procId -Force -ErrorAction Stop
        } catch {
            Write-Log "Could not stop supervisor PID $procId : $($_.Exception.Message)" 'WARN'
        }
    }
    Remove-Item -LiteralPath $script:PidFile -Force -ErrorAction SilentlyContinue
}

# ─── PROCESS START ───────────────────────────────────────────────────────
function Start-ServiceProcess {
    param(
        [string]$Name,
        [hashtable]$Python,
        [string[]]$ScriptArgs,
        [string]$LogPrefix
    )
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $outLog = Join-Path $script:LogDir ('{0}_{1}.out.log' -f $LogPrefix, $stamp)
    $errLog = Join-Path $script:LogDir ('{0}_{1}.err.log' -f $LogPrefix, $stamp)
    $argList = @($Python.Prefix)
    for ($i = 0; $i -lt $ScriptArgs.Count; $i++) {
        $a = $ScriptArgs[$i]
        if ($i -eq 0 -or $a -match '\s') { $a = '"' + $a + '"' }
        $argList += $a
    }
    $proc = Start-Process -FilePath $Python.Path `
        -ArgumentList $argList `
        -WorkingDirectory $script:Root `
        -WindowStyle Hidden `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -PassThru
    Write-Log "Started $Name (PID $($proc.Id)) -> $LogPrefix"
    return $proc
}

# ─── HEALTH ──────────────────────────────────────────────────────────────
function Get-Json {
    param([string]$Url, [int]$TimeoutSec = 5)
    try {
        return Invoke-RestMethod -Uri $Url -TimeoutSec $TimeoutSec -ErrorAction Stop
    } catch {
        return $null
    }
}

function Test-HttpOk {
    param([string]$Url, [int]$TimeoutSec = 5)
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec -ErrorAction Stop
        return ($r.StatusCode -eq 200)
    } catch {
        return $false
    }
}

function Wait-Healthy {
    param([string]$Url, [string]$Label, [int]$TimeoutSec)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $attempt = 0
    while ((Get-Date) -lt $deadline) {
        $attempt++
        if (Test-HttpOk -Url $Url) {
            Write-Log "OK: $Label healthy at $Url (attempt $attempt)"
            return $true
        }
        Start-Sleep -Seconds 1
    }
    Write-Log "FAIL: $Label not answering at $Url after ${TimeoutSec}s ($attempt attempts)" 'ERROR'
    return $false
}

function Invoke-SmokeTest {
    $body = @{
        model     = 'openai/gpt-oss-20b'
        messages  = @(@{ role = 'user'; content = 'ping' })
        max_tokens = 1
        stream    = $false
    } | ConvertTo-Json -Depth 5

    $ok = $true
    try {
        $r = Invoke-RestMethod -Uri "$script:BridgeUrl/v1/chat/completions" -Method Post `
            -ContentType 'application/json' -Body $body -TimeoutSec 90 -ErrorAction Stop
        if ($r.choices) { Write-Log "OK: Groq bridge completion via :$BridgePort (model $($r.model))" }
        else { Write-Log "FAIL: Groq bridge returned no choices" 'ERROR'; $ok = $false }
    } catch {
        Write-Log "FAIL: Groq bridge completion - $($_.Exception.Message)" 'ERROR'
        $ok = $false
    }

    try {
        $r2 = Invoke-RestMethod -Uri "$script:ConsoleUrl/v1/chat/completions" -Method Post `
            -ContentType 'application/json' -Body $body -TimeoutSec 90 -ErrorAction Stop
        if ($r2.choices) { Write-Log "OK: Provider Console routed completion via :$ConsolePort" }
        else { Write-Log "FAIL: Provider Console returned no choices" 'ERROR'; $ok = $false }
    } catch {
        Write-Log "FAIL: Provider Console completion - $($_.Exception.Message)" 'ERROR'
        $ok = $false
    }
    return $ok
}

function Test-StackHealthy {
    $bridgeOk  = Test-HttpOk "$script:BridgeUrl/health"
    $consoleOk = Test-HttpOk "$script:ConsoleUrl/health"
    return ($bridgeOk -and $consoleOk)
}

# ─── START / STOP ────────────────────────────────────────────────────────
function Start-BruceStack {
    Write-Log '=== BruceAI start requested ==='
    Clear-HermesRequestDumps | Out-Null

    # 1. Keys from .env (placeholders fall back to real local keys)
    $keyInfo = Get-EnvKeySources
    Set-ProcessEnv -Map $keyInfo.Values
    Report-KeySources -Sources $keyInfo.Sources -Values $keyInfo.Values

    # 2. Python + deps
    $python = Resolve-Python
    Write-Log "Python: $($python.Path)"
    Test-PythonDeps -Python $python

    # 3. Free the ports - this is what stops Errno 10048 on restart
    $freed = $true
    $freed = (Stop-PortOwners -Port $BridgePort) -and $freed
    $freed = (Stop-PortOwners -Port $ConsolePort) -and $freed
    if (-not $freed) {
        Write-Log 'Could not free the ports - aborting start.' 'ERROR'
        return $false
    }

    # 4. Bridge first: the console health check reports on it
    $script:BridgePid = Start-ServiceProcess -Name 'Groq Bridge' -Python $python `
        -ScriptArgs @($script:BridgeScript, '--port', "$BridgePort", '--host', '127.0.0.1') `
        -LogPrefix 'groq_bridge'
    if (-not $NoHealthCheck) {
        if (-not (Wait-Healthy -Url "$script:BridgeUrl/health" -Label 'Groq Bridge' -TimeoutSec $StartupTimeoutSec)) {
            return $false
        }
        $models = Get-Json "$script:BridgeUrl/v1/models"
        if (-not $models) {
            Write-Log 'Groq Bridge /v1/models failed - GROQ_API_KEY is not usable.' 'ERROR'
            return $false
        }
        Write-Log "OK: Groq Bridge serves $($models.data.Count) models"
    }

    # 5. Provider Console (Hermes needs this up for the model picker)
    $script:ConsolePid = Start-ServiceProcess -Name 'Provider Console' -Python $python `
        -ScriptArgs @($script:ConsoleScript) `
        -LogPrefix 'provider_console'
    if (-not $NoHealthCheck) {
        if (-not (Wait-Healthy -Url "$script:ConsoleUrl/health" -Label 'Provider Console' -TimeoutSec $StartupTimeoutSec)) {
            return $false
        }
    }

    # 6. Verification
    if (-not $NoHealthCheck) {
        $bh = Get-Json "$script:BridgeUrl/health"
        $ch = Get-Json "$script:ConsoleUrl/health"
        if (-not $bh -or $bh.status -ne 'ok') { Write-Log 'Bridge health check failed' 'ERROR'; return $false }
        if (-not $ch -or $ch.status -ne 'ok') { Write-Log 'Console health check failed' 'ERROR'; return $false }
        if ($ch.port -ne $ConsolePort) { Write-Log "Console reports port $($ch.port), expected $ConsolePort" 'ERROR'; return $false }
        if ($ch.groq_bridge -ne 'healthy') { Write-Log "Console cannot reach the bridge: $($ch.groq_bridge)" 'ERROR'; return $false }
        if (-not $ch.openrouter_configured) { Write-Log 'OPENROUTER_API_KEY not active in the console - OpenRouter models will fail.' 'WARN' }
        if (-not $ch.opencode_configured) { Write-Log 'OPENCODE key not active in the console - opencode models will fail.' 'WARN' }

        $cm = Get-Json "$script:ConsoleUrl/v1/models"
        if (-not $cm -or $cm.data.Count -lt 9) {
            Write-Log "Console serves $(if ($cm) { $cm.data.Count } else { 0 }) models (expected >= 9)" 'ERROR'
            return $false
        }
        Write-Log "OK: Provider Console healthy on :$ConsolePort, groq_bridge=$($ch.groq_bridge), models=$($cm.data.Count)"

        if ($SmokeTest) {
            if (-not (Invoke-SmokeTest)) { return $false }
        }
    }
    Write-Log 'BruceAI stack is up.'
    return $true
}

function Stop-BruceStack {
    # Supervisor first, otherwise it brings the services straight back up.
    Stop-Supervisors
    $ok = $true
    $ok = (Stop-PortOwners -Port $ConsolePort) -and $ok
    $ok = (Stop-PortOwners -Port $BridgePort) -and $ok
    if ($ok) { Write-Log "Stopped BruceAI services; ports $BridgePort and $ConsolePort are free." }
    else { Write-Log 'Some ports could not be freed.' 'ERROR' }
    return $ok
}

# ─── STATUS ──────────────────────────────────────────────────────────────
function Clear-HermesRequestDumps {
    <# HERMES_DUMP_REQUESTS writes a ~96KB JSON per agent request - and per retry, so one
       failing turn can write 14 of them, and yesterday's storm alone filled 399MB. Keeps the
       newest files within both an age and a size budget, so a burst can never refill the disk.
       Returns files removed. #>
    param([int]$KeepDays = 1, [int]$KeepMB = 32)

    if (-not $env:LOCALAPPDATA) { return 0 }
    $profilesRoot = Join-Path $env:LOCALAPPDATA 'hermes\profiles'
    if (-not (Test-Path -LiteralPath $profilesRoot)) { return 0 }

    $all = @()
    foreach ($profile in (Get-ChildItem -LiteralPath $profilesRoot -Directory -ErrorAction SilentlyContinue)) {
        $sessions = Join-Path $profile.FullName 'sessions'
        if (-not (Test-Path -LiteralPath $sessions)) { continue }
        $all += @(Get-ChildItem -LiteralPath $sessions -File -Filter 'request_dump_*.json' -ErrorAction SilentlyContinue)
    }
    if ($all.Count -eq 0) { return 0 }

    $cutoff = (Get-Date).AddDays(-$KeepDays)
    $budget = $KeepMB * 1MB
    $keep = New-Object 'System.Collections.Generic.HashSet[string]'
    $keptBytes = 0
    foreach ($f in ($all | Sort-Object LastWriteTime -Descending)) {
        if ($f.LastWriteTime -lt $cutoff) { break }   # sorted newest first: the rest are older too
        if ($keptBytes -ge $budget) { break }         # size budget spent: only newer files would qualify
        [void]$keep.Add($f.FullName)
        $keptBytes += $f.Length
    }

    $old = @($all | Where-Object { -not $keep.Contains($_.FullName) })
    if ($old.Count -eq 0) { return 0 }

    $freed = ($old | Measure-Object -Property Length -Sum).Sum
    $old | Remove-Item -Force -ErrorAction SilentlyContinue
    Write-Log ("Pruned {0} request dumps ({1} MB freed; kept newest within {2} day(s) / {3} MB)" -f `
        $old.Count, [int]($freed / 1MB), $KeepDays, $KeepMB)
    return $old.Count
}

function Invoke-HttpJson {
    <# Minimal HTTP that behaves the same on Windows PowerShell 5.1 (the production shell, where
       Invoke-WebRequest without -UseBasicParsing tries to parse responses as HTML and throws
       NullReferenceException) and PowerShell 7. Returns @{ StatusCode; Body } and never throws. #>
    param(
        [string]$Method = 'GET',
        [string]$Uri,
        [hashtable]$Headers = @{},
        [string]$Body,
        [int]$TimeoutSec = 15
    )
    if (-not ('System.Net.Http.HttpClient' -as [type])) {
        Add-Type -AssemblyName System.Net.Http
    }
    $client = New-Object System.Net.Http.HttpClient
    $client.Timeout = [TimeSpan]::FromSeconds($TimeoutSec)
    try {
        foreach ($h in $Headers.Keys) {
            $client.DefaultRequestHeaders.TryAddWithoutValidation([string]$h, [string]$Headers[$h]) | Out-Null
        }
        if ($Method -eq 'POST') {
            $content = New-Object System.Net.Http.StringContent($Body, [Text.Encoding]::UTF8, 'application/json')
            $resp = $client.PostAsync($Uri, $content).GetAwaiter().GetResult()
        } else {
            $resp = $client.GetAsync($Uri).GetAwaiter().GetResult()
        }
        $text = $resp.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        return @{ StatusCode = [int]$resp.StatusCode; Body = $text }
    } catch {
        return @{ StatusCode = 0; Body = $_.Exception.Message }
    } finally {
        $client.Dispose()
    }
}

function Show-ProviderQuotas {
    <# Read-only upstream checks. Local /health only proves the process is up - it cannot tell
       you that Groq is rejecting oversized payloads or that OpenRouter has no credits left,
       which are the two ways every agent call can fail while everything looks green. #>
    $keyInfo = Get-EnvKeySources

    $groq = $keyInfo.Values['GROQ_API_KEY']
    if (-not (Test-RealKey -Value $groq)) {
        Write-Log 'Groq key      : not configured' 'WARN'
    } else {
        $r = Invoke-HttpJson -Uri 'https://api.groq.com/openai/v1/models' -Headers @{ Authorization = "Bearer $groq" } -TimeoutSec 8
        switch ($r.StatusCode) {
            200 { Write-Log 'Groq key      : valid (free tier - per-minute token caps apply)' }
            0   { Write-Log "Groq key      : check failed ($($r.Body))" 'WARN' }
            401 { Write-Log 'Groq key      : INVALID (HTTP 401) - replace the key' 'WARN' }
            default { Write-Log "Groq key      : unexpected response (HTTP $($r.StatusCode))" 'WARN' }
        }
    }

    $orKey = $keyInfo.Values['OPENROUTER_API_KEY']
    if (-not (Test-RealKey -Value $orKey)) {
        Write-Log 'OpenRouter key: not configured' 'WARN'
    } else {
        # Affordability probe: when credits run out OpenRouter answers 402 and states how many
        # completion tokens the balance still buys - that number, not /api/v1/key's spending
        # limit, is the real signal (the limit can show $50 remaining while the balance is 0).
        $probe = '{"model":"openai/gpt-oss-120b","messages":[{"role":"user","content":"hi"}],"max_tokens":4096}'
        $r = Invoke-HttpJson -Method POST -Uri 'https://openrouter.ai/api/v1/chat/completions' `
            -Headers @{ Authorization = "Bearer $orKey"; 'X-Title' = 'BruceAI status check' } `
            -Body $probe -TimeoutSec 20
        switch ($r.StatusCode) {
            200 { Write-Log 'OpenRouter key: valid, credits available (probe completed)' }
            402 {
                if ($r.Body -match 'can only afford (\d+)') {
                    Write-Log "OpenRouter key: OUT OF CREDITS - balance buys only $($matches[1]) completion tokens; agent calls will 402" 'WARN'
                } else {
                    Write-Log 'OpenRouter key: OUT OF CREDITS (HTTP 402) - add credits or lower max_tokens' 'WARN'
                }
            }
            401 { Write-Log 'OpenRouter key: INVALID (HTTP 401) - replace the key' 'WARN' }
            0   { Write-Log "OpenRouter key: check failed ($($r.Body))" 'WARN' }
            default { Write-Log "OpenRouter key: unexpected response (HTTP $($r.StatusCode))" 'WARN' }
        }
    }
}

function Show-Status {
    Write-Log '--- BruceAI status ---'
    $sup = Get-SupervisorPids
    if ($sup.Count) { Write-Log "Supervisor: running (PID $($sup -join ', '))" }
    else { Write-Log 'Supervisor: not running' 'WARN' }

    foreach ($port in @($BridgePort, $ConsolePort)) {
        $owners = Get-PortOwners -Port $port
        if ($owners.Count -eq 0) { Write-Log "Port $port : FREE" 'WARN' }
        foreach ($procId in $owners) {
            $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
            if ($p) {
                try { $started = $p.StartTime } catch { $started = 'unknown' }
                Write-Log ("Port {0} : PID {1} {2} started {3}" -f $port, $procId, $p.ProcessName, $started)
            }
        }
    }

    $bh = Get-Json "$script:BridgeUrl/health"
    if ($bh) { Write-Log "Bridge  /health : $($bh | ConvertTo-Json -Compress)" }
    else { Write-Log "Bridge  /health : unreachable" 'WARN' }

    $ch = Get-Json "$script:ConsoleUrl/health"
    if ($ch) { Write-Log "Console /health : $($ch | ConvertTo-Json -Compress)" }
    else { Write-Log "Console /health : unreachable" 'WARN' }

    $cm = Get-Json "$script:ConsoleUrl/v1/models"
    if ($cm) { Write-Log "Console serves $($cm.data.Count) models" }

    Show-ProviderQuotas

    try {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
        $info = Get-ScheduledTaskInfo -TaskName $TaskName
        Write-Log "Scheduled task '$TaskName': $($info.LastRunTime) result=$($info.LastTaskResult) next=$($info.NextRunTime)"
    } catch {
        Write-Log "Scheduled task '$TaskName': not installed"
    }

    $lnk = Get-StartupShortcutPath
    if (Test-Path -LiteralPath $lnk) { Write-Log "Startup shortcut: present ($lnk)" }
    else { Write-Log 'Startup shortcut: not installed (run InstallTask)' }
}

# ─── AUTO-START (Task Scheduler, with Startup-folder fallback) ───────────
function Get-StartupShortcutPath {
    $startup = [Environment]::GetFolderPath('Startup')
    return (Join-Path $startup 'BruceAI Services.lnk')
}

function Install-StartupShortcut {
    $psCommand = if ($PSCommandPath) { $PSCommandPath } else { Join-Path $script:Root 'start_bruceai.ps1' }
    $hostExe = (Get-Process -Id $PID).Path
    if (-not $hostExe) { $hostExe = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" }
    $lnkPath = Get-StartupShortcutPath

    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($lnkPath)
    $lnk.TargetPath = $hostExe
    $lnk.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" Supervise' -f $psCommand
    $lnk.WorkingDirectory = $script:Root
    $lnk.WindowStyle = 7   # minimised; -WindowStyle Hidden keeps it out of the way
    $lnk.Description = 'BruceAI Groq Bridge (:8080) + Provider Console (:9001)'
    $lnk.Save()

    Write-Log "Installed Startup-folder shortcut: $lnkPath"
    Write-Log 'It launches the same supervisor as the scheduled task (runs at every logon).'
}

function Install-AutoStart {
    $psCommand = if ($PSCommandPath) { $PSCommandPath } else { Join-Path $script:Root 'start_bruceai.ps1' }
    $hostExe = (Get-Process -Id $PID).Path
    if (-not $hostExe) { $hostExe = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" }

    $argString = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" Supervise' -f $psCommand
    $action = New-ScheduledTaskAction -Execute $hostExe -Argument $argString -WorkingDirectory $script:Root

    $user = '{0}\{1}' -f $env:USERDOMAIN, $env:USERNAME
    $triggers = @()

    # Logon trigger with a short delay: services must beat Hermes' gateway to :9001.
    $tLogon = New-ScheduledTaskTrigger -AtLogOn -User $user
    $tLogon.Delay = 'PT5S'
    $triggers += $tLogon

    # Boot trigger: honoured once a user session exists (principal is interactive).
    $tBoot = New-ScheduledTaskTrigger -AtStartup
    $tBoot.Delay = 'PT30S'
    $triggers += $tBoot

    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -MultipleInstances IgnoreNew `
        -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit (New-TimeSpan -Days 3650) `
        -Priority 4

    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

    try {
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers `
            -Settings $settings -Principal $principal `
            -Description 'BruceAI: Groq Bridge (:8080) and Provider Console (:9001) supervisor' -Force -ErrorAction Stop | Out-Null
        Write-Log "Installed scheduled task '$TaskName' (logon +5s, boot +30s, auto-restart on failure)."
        return
    } catch {
        Write-Log "Task Scheduler refused registration ($($_.Exception.Message)) - usually UAC." 'WARN'
        Write-Log 'Falling back to the Startup folder, which needs no elevation.' 'WARN'
    }

    Install-StartupShortcut
}

function Uninstall-AutoStart {
    $removed = $false
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
        Write-Log "Removed scheduled task '$TaskName'."
        $removed = $true
    } catch { }

    $lnk = Get-StartupShortcutPath
    if (Test-Path -LiteralPath $lnk) {
        Remove-Item -LiteralPath $lnk -Force
        Write-Log "Removed Startup-folder shortcut: $lnk"
        $removed = $true
    }

    Stop-Supervisors
    if (-not $removed) { Write-Log 'Nothing to uninstall (no task, no shortcut).' 'WARN' }
}

# ─── SUPERVISOR ──────────────────────────────────────────────────────────
function Watch-Supervisor {
    Write-Log "Supervisor started (checking every ${MonitorIntervalSec}s)."
    $failStreak = 0
    try {
        while ($true) {
            Start-Sleep -Seconds $MonitorIntervalSec
            if (Test-StackHealthy) {
                if ($failStreak -gt 0) { Write-Log 'Services healthy again.' }
                $failStreak = 0
                continue
            }
            $failStreak++
            if ($failStreak -lt 2) {
                Write-Log "Unhealthy check $failStreak/2 - waiting before repair" 'WARN'
                continue
            }
            $failStreak = 0
            Write-Log 'Repairing BruceAI services...' 'WARN'
            Start-BruceStack | Out-Null
        }
    } finally {
        Write-Log 'Supervisor exiting (services are left running unless Stop was requested).'
    }
}

# ─── DISPATCH ────────────────────────────────────────────────────────────
$exitCode = 0
switch ($Action) {
    'Start' {
        if (-not (Start-BruceStack)) { $exitCode = 1 }
    }
    'Stop' {
        if (-not (Stop-BruceStack)) { $exitCode = 1 }
    }
    'Restart' {
        Stop-BruceStack | Out-Null
        if (-not (Start-BruceStack)) { $exitCode = 1 }
    }
    'Status' {
        Show-Status
    }
    'Prune' {
        Clear-HermesRequestDumps | Out-Null
    }
    'InstallTask' {
        Install-AutoStart
    }
    'UninstallTask' {
        Uninstall-AutoStart
    }
    'Supervise' {
        # Singleton: the Startup shortcut and a scheduled task can both fire at logon.
        $others = Get-SupervisorPids
        if ($others.Count -gt 0) {
            Write-Log "Supervisor already running (PID $($others -join ', ')) - exiting this instance."
            break
        }
        Set-Content -LiteralPath $script:PidFile -Value $PID -Encoding ASCII
        try {
            if (-not (Start-BruceStack)) {
                Write-Log 'Initial start failed - supervisor will keep retrying.' 'ERROR'
                $exitCode = 1
            } else {
                Watch-Supervisor
            }
        } finally {
            Remove-Item -LiteralPath $script:PidFile -Force -ErrorAction SilentlyContinue
        }
    }
}
exit $exitCode
