<#
.SYNOPSIS
  Doctor Prospector standalone installer for Windows (no Docker needed).

.DESCRIPTION
  1. Checks for Python 3.11+
  2. Creates a virtual environment in .venv and installs dependencies
  3. Creates .env from .env.example with a random SECRET_KEY
  4. Builds the web pages if frontend/dist is missing (needs Node.js)
  5. Creates the SQLite database
  6. Loads the physician volume history from the bundled snapshot (seconds)

  Safe to re-run: existing .venv, .env and database are kept.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File install.ps1
  powershell -ExecutionPolicy Bypass -File install.ps1 -LoadHistory   # also fetch years newer than the snapshot
#>
param(
    [switch]$LoadHistory    # after the snapshot, fetch any newer years from CMS
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Fail($msg) { Write-Host "`nERROR: $msg" -ForegroundColor Red; exit 1 }

# --- 1. Python ----------------------------------------------------------
Step "Checking Python"

# Run a python command given as an array like @("py", "-3.12") or @("python")
function Invoke-Py([string[]]$cmd, [string[]]$pyArgs) {
    $exe = $cmd[0]
    $pre = if ($cmd.Length -gt 1) { $cmd[1..($cmd.Length - 1)] } else { @() }
    & $exe @pre @pyArgs
}

$python = $null
foreach ($candidate in @("py -3.12", "py -3.13", "py -3.11", "python", "python3")) {
    $parts = $candidate.Split(" ")
    try {
        $version = Invoke-Py $parts @("-c", "import sys; print('%d.%d' % sys.version_info[:2])") 2>$null
        if ($LASTEXITCODE -eq 0 -and $version) {
            $major, $minor = $version.Trim().Split(".") | ForEach-Object { [int]$_ }
            if ($major -eq 3 -and $minor -ge 11) { $python = $parts; break }
        }
    } catch { }
}
if (-not $python) {
    Fail "Python 3.11 or newer is required. Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then re-run this script."
}
Write-Host "Using $($python -join ' ') (Python $version)"

# --- 2. Virtual environment ---------------------------------------------
$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Step "Creating virtual environment (.venv)"
    Invoke-Py $python @("-m", "venv", ".venv")
    if ($LASTEXITCODE -ne 0) { Fail "Could not create .venv" }
} else {
    Step "Using existing virtual environment (.venv)"
}

Step "Installing dependencies (a few minutes the first time)"
& $venvPython -m pip install --upgrade pip --quiet
if ($LASTEXITCODE -ne 0) { Fail "pip upgrade failed" }
& $venvPython -m pip install -e . -e ./backend --quiet
if ($LASTEXITCODE -ne 0) { Fail "Dependency install failed (see messages above)" }

# --- 3. .env --------------------------------------------------------------
if (-not (Test-Path ".env")) {
    Step "Creating .env from .env.example"
    $secret = & $venvPython -c "import secrets; print(secrets.token_urlsafe(48))"
    (Get-Content ".env.example" -Raw) -replace "(?m)^SECRET_KEY=.*$", "SECRET_KEY=$secret" |
        Set-Content ".env" -Encoding ascii -NoNewline
} else {
    Step "Keeping existing .env"
}

# --- 4. Web pages -----------------------------------------------------------
if (-not (Test-Path "frontend\dist\index.html")) {
    Step "Building the web pages"
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        Push-Location frontend
        npm ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { npm install --no-audit --no-fund }
        npm run build
        $built = $LASTEXITCODE -eq 0
        Pop-Location
        if (-not $built) { Fail "Frontend build failed (see messages above)" }
    } else {
        Write-Host "Node.js isn't installed, so the web pages can't be built here." -ForegroundColor Yellow
        Write-Host "Either install Node.js 20+ (https://nodejs.org) and re-run this script," -ForegroundColor Yellow
        Write-Host "or download a release that includes frontend/dist." -ForegroundColor Yellow
    }
} else {
    Step "Web pages already built (frontend\dist)"
}

# --- 5. Database ----------------------------------------------------------
Step "Creating/updating the database"
$env:PYTHONPATH = "$Root\src;$Root\backend"
Push-Location backend
& $venvPython -m alembic upgrade head
$migrated = $LASTEXITCODE -eq 0
Pop-Location
if (-not $migrated) { Fail "Database setup failed (see messages above)" }

# --- 6. Physician history ---------------------------------------------------
# Published CMS years never change, so the repo ships them as a snapshot
# (data/seed). Importing takes seconds; refresh_all fetches newer years later.
Step "Loading physician history (bundled snapshot)"
& $venvPython scripts\history_seed.py import
if ($LASTEXITCODE -ne 0) {
    Write-Host "Snapshot import failed; you can fetch the history from CMS instead (35-60 min):" -ForegroundColor Yellow
    Write-Host "  .venv\Scripts\python scripts\refresh_all.py --only db_history" -ForegroundColor Yellow
}
if ($LoadHistory) {
    Step "Fetching any newer years from CMS"
    & $venvPython scripts\refresh_all.py --only db_history
}

Write-Host "`nInstall complete. Start Doctor Prospector with:" -ForegroundColor Green
Write-Host "  powershell -ExecutionPolicy Bypass -File run.ps1" -ForegroundColor Green
