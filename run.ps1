<#
.SYNOPSIS
  Start Doctor Prospector (standalone) and open it in the browser.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File run.ps1
  powershell -ExecutionPolicy Bypass -File run.ps1 -NoBrowser
#>
param([switch]$NoBrowser)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Not installed yet. Run: powershell -ExecutionPolicy Bypass -File install.ps1" -ForegroundColor Red
    exit 1
}

# HOST / PORT from .env (defaults match .env.example)
$listenHost = "127.0.0.1"; $port = "8000"
if (Test-Path "$Root\.env") {
    foreach ($line in Get-Content "$Root\.env") {
        if ($line -match "^\s*HOST\s*=\s*(.+?)\s*$") { $listenHost = $Matches[1] }
        if ($line -match "^\s*PORT\s*=\s*(\d+)\s*$") { $port = $Matches[1] }
    }
}
$browseHost = if ($listenHost -eq "0.0.0.0") { "localhost" } else { $listenHost }
$url = "http://${browseHost}:$port"

$env:PYTHONPATH = "$Root\src;$Root\backend"
$env:PYTHONIOENCODING = "utf-8"

if (-not $NoBrowser) {
    # Open the browser once the server answers (up to ~60 s)
    Start-Job -ScriptBlock {
        param($u)
        for ($i = 0; $i -lt 60; $i++) {
            try { Invoke-WebRequest "$u/api/v1/health" -UseBasicParsing -TimeoutSec 2 | Out-Null; Start-Process $u; break }
            catch { Start-Sleep -Seconds 1 }
        }
    } -ArgumentList $url | Out-Null
}

Write-Host "Doctor Prospector running at $url  (Ctrl+C to stop)" -ForegroundColor Green
Set-Location "$Root\backend"
& $venvPython -m uvicorn app.main:app --host $listenHost --port $port
