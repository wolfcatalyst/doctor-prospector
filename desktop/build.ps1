<#
.SYNOPSIS
  Build the Doctor Prospector Windows installer (dist\installer\DoctorProspector-Setup-<version>.exe).

.DESCRIPTION
  1. Creates a build-only virtual environment (.venv-build) with the app's
     dependencies plus PyInstaller, pywebview and Pillow
  2. Builds the web pages (needs Node.js 20+)
  3. Bundles Python + everything into dist\DoctorProspector (PyInstaller)
  4. Optionally signs DoctorProspector.exe
  5. Builds the installer with Inno Setup 6, signing the setup and the
     uninstaller when -SignCommand is given

  Needs: Python 3.11+, Node.js 20+, Inno Setup 6
         (winget install JRSoftware.InnoSetup)

.PARAMETER SignCommand
  Your signing command, with $f where the file path goes. Use single quotes
  so PowerShell leaves $f alone, e.g.:
    -SignCommand 'signtool sign /sha1 <THUMBPRINT> /fd sha256 /tr http://timestamp.digicert.com /td sha256 $f'
  Leave it out for an unsigned build (sign later yourself).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File desktop\build.ps1
#>
param(
    [string]$SignCommand = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Fail($msg) { Write-Host "`nBUILD FAILED: $msg" -ForegroundColor Red; exit 1 }
function Sign-File($path) {
    if (-not $SignCommand) { return }
    $cmd = $SignCommand.Replace('$f', "`"$path`"")
    Write-Host "Signing $path"
    cmd /c $cmd
    if ($LASTEXITCODE -ne 0) { Fail "signing failed for $path" }
}

# --- version -------------------------------------------------------------------
$version = (Select-String -Path "backend\pyproject.toml" -Pattern '^version\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
if (-not $version) { Fail "couldn't read version from backend\pyproject.toml" }
Write-Host "Doctor Prospector $version"

# --- 1. build environment ----------------------------------------------------
Step "Build environment (.venv-build)"
$py = Join-Path $Root ".venv-build\Scripts\python.exe"
if (-not (Test-Path $py)) {
    $base = $null
    foreach ($c in @(@("py", "-3.12"), @("py", "-3.11"), @("python"))) {
        $exe = $c[0]; $pre = if ($c.Length -gt 1) { $c[1..($c.Length - 1)] } else { @() }
        try {
            $ok = & $exe @pre -c "import sys; print(sys.version_info >= (3, 11))" 2>$null
            if ($LASTEXITCODE -eq 0 -and $ok -eq "True") { $base = $c; break }
        } catch { }
    }
    if (-not $base) { Fail "Python 3.11+ not found" }
    $exe = $base[0]; $pre = if ($base.Length -gt 1) { $base[1..($base.Length - 1)] } else { @() }
    & $exe @pre -m venv .venv-build
    if ($LASTEXITCODE -ne 0) { Fail "couldn't create .venv-build" }
}
& $py -m pip install --upgrade pip --quiet
& $py -m pip install -e . -e ./backend pyinstaller pywebview pillow --quiet
if ($LASTEXITCODE -ne 0) { Fail "dependency install failed" }

# --- 2. web pages ----------------------------------------------------------------
Step "Building the web pages"
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { Fail "Node.js/npm not found (install Node.js 20+)" }
Push-Location frontend
npm ci --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "npm ci failed" }
npm run build
$built = $LASTEXITCODE -eq 0
Pop-Location
if (-not $built) { Fail "frontend build failed" }

# --- bundled data checks -----------------------------------------------------------
if (-not (Test-Path "data\seed\physician_volumes.csv.gz")) {
    Fail "data\seed\physician_volumes.csv.gz missing. Export it from a loaded database: python scripts\history_seed.py export"
}

# --- icon + version resource ---------------------------------------------------------
if (-not (Test-Path "desktop\icon.ico")) {
    Step "Generating placeholder icon (replace desktop\icon.ico with your own)"
    & $py desktop\make_icon.py desktop\icon.ico
    if ($LASTEXITCODE -ne 0) { Fail "icon generation failed" }
}
New-Item -ItemType Directory -Force build | Out-Null
$v = ($version.Split(".") + @("0", "0", "0"))[0..3] -join ", "
@"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($v), prodvers=($v)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'Wolf (github.com/wolfcatalyst)'),
    StringStruct('FileDescription', 'Doctor Prospector'),
    StringStruct('FileVersion', '$version'),
    StringStruct('InternalName', 'DoctorProspector'),
    StringStruct('OriginalFilename', 'DoctorProspector.exe'),
    StringStruct('ProductName', 'Doctor Prospector'),
    StringStruct('ProductVersion', '$version')])]),
  VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
"@ | Set-Content build\version_info.txt -Encoding utf8

# --- 3. bundle ---------------------------------------------------------------------
Step "Bundling the app (PyInstaller)"
& $py -m PyInstaller desktop\DoctorProspector.spec --noconfirm --clean --distpath dist --workpath build\pyinstaller
if ($LASTEXITCODE -ne 0) { Fail "PyInstaller failed" }
$appExe = "dist\DoctorProspector\DoctorProspector.exe"
if (-not (Test-Path $appExe)) { Fail "$appExe was not produced" }

# --- 4. sign the app ---------------------------------------------------------------
if ($SignCommand) { Step "Signing the app"; Sign-File (Resolve-Path $appExe) }

# --- 5. installer ------------------------------------------------------------------
Step "Building the installer (Inno Setup)"
$iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { Fail "Inno Setup 6 not found. Install it: winget install JRSoftware.InnoSetup" }

$isccArgs = @("/DAppVersion=$version", "/Qp", "desktop\installer.iss")
if ($SignCommand) {
    # Inno signs the setup and its uninstaller with this ($f = file)
    $isccArgs = @("/DSIGN", "/Scustom=$SignCommand") + $isccArgs
}
& $iscc @isccArgs
if ($LASTEXITCODE -ne 0) { Fail "Inno Setup failed" }

$setup = "dist\installer\DoctorProspector-Setup-$version.exe"
$size = [math]::Round((Get-Item $setup).Length / 1MB, 1)
Write-Host "`nBuilt $setup ($size MB)" -ForegroundColor Green
if (-not $SignCommand) {
    Write-Host "Unsigned. To sign: re-run with -SignCommand, or sign dist\DoctorProspector\DoctorProspector.exe" -ForegroundColor Yellow
    Write-Host "BEFORE building the installer, then sign the setup .exe." -ForegroundColor Yellow
}
