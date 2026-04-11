# ─────────────────────────────────────────────────────────────────────────────
# build-release.ps1  —  Build the Kendr desktop release package (Windows)
#
# Usage (run from repo root or scripts/):
#   .\scripts\build-release.ps1              # NSIS installer for Windows x64
#   .\scripts\build-release.ps1 -Target all  # all platforms (requires WSL for Linux)
#   .\scripts\build-release.ps1 -SkipSign    # skip code-signing
#
# Output: electron-app\dist\
# ─────────────────────────────────────────────────────────────────────────────
[CmdletBinding()]
param(
    [ValidateSet('win', 'mac', 'linux', 'all')]
    [string]$Target = 'win',
    [switch]$SkipSign
)

$ErrorActionPreference = 'Stop'

$RootDir     = Split-Path -Parent $PSScriptRoot
$ElectronDir = Join-Path $RootDir 'electron-app'
$ResourcesDir = Join-Path $ElectronDir 'resources'

function Write-Info  { param($m) Write-Host "  > $m" -ForegroundColor Cyan }
function Write-Ok    { param($m) Write-Host "  v $m" -ForegroundColor Green }
function Write-Warn  { param($m) Write-Host "  ! $m" -ForegroundColor Yellow }
function Write-Err   { param($m) Write-Host "`n  x ERROR: $m`n" -ForegroundColor Red; exit 1 }

Write-Host "`n  ⚡ Kendr Desktop — Release Builder (Windows)`n" -ForegroundColor Cyan

# ── 1. Prerequisites ─────────────────────────────────────────────────────────
Write-Info "Checking prerequisites…"

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Err "Node.js is required. Install from https://nodejs.org"
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Err "npm is required. Install from https://nodejs.org"
}

$nodeVer = (node --version) -replace 'v', ''
$nodeMajor = [int]($nodeVer.Split('.')[0])
if ($nodeMajor -lt 18) { Write-Err "Node.js 18+ required. Found: v$nodeVer" }

Write-Ok "Node $(node --version), npm $(npm --version)"

# ── 2. Icon check ────────────────────────────────────────────────────────────
Write-Info "Checking app icons…"
$missingIcons = @()
if (-not (Test-Path "$ResourcesDir\icon.png"))  { $missingIcons += "resources\icon.png  (1024x1024 PNG)" }
if (-not (Test-Path "$ResourcesDir\icon.ico"))  { $missingIcons += "resources\icon.ico  (Windows multi-res ICO)" }
if (-not (Test-Path "$ResourcesDir\icon.icns")) { $missingIcons += "resources\icon.icns (macOS icon bundle)" }

if ($missingIcons.Count -gt 0) {
    Write-Warn "Missing icons (builds will fall back to Electron defaults):"
    $missingIcons | ForEach-Object { Write-Host "    • electron-app\$_" -ForegroundColor Yellow }
    Write-Host ""
    Write-Host "  Generate icons from a 1024x1024 PNG using:" -ForegroundColor White
    Write-Host "    .\scripts\build-icons.ps1 C:\path\to\logo.png" -ForegroundColor Cyan
    Write-Host ""
}

# ── 3. Node dependencies ──────────────────────────────────────────────────────
Write-Info "Installing Node dependencies…"
Push-Location $ElectronDir
npm install --silent
Write-Ok "Node dependencies installed"

# Rebuild native modules (node-pty)
Write-Info "Rebuilding native modules (node-pty)…"
try { npm run rebuild 2>&1 | Select-Object -Last 3 | ForEach-Object { Write-Host "    $_" } }
catch { Write-Warn "Rebuild had warnings (may be OK)" }

# ── 4. Electron-vite build ────────────────────────────────────────────────────
Write-Info "Transpiling with electron-vite…"
npm run build
Write-Ok "Electron build complete"

# ── 5. Code-signing env ───────────────────────────────────────────────────────
if (-not $SkipSign) {
    if (-not $env:CSC_LINK) {
        Write-Warn "CSC_LINK not set — Windows build will be unsigned."
        Write-Warn "  Set `$env:CSC_LINK = 'C:\path\cert.p12'` and `$env:CSC_KEY_PASSWORD to sign."
    }
}

# ── 6. electron-builder ───────────────────────────────────────────────────────
$builderArgs = switch ($Target) {
    'win'   { '--win' }
    'mac'   { '--mac' }
    'linux' { '--linux' }
    'all'   { '--win --linux' }  # Mac requires a macOS host
}

Write-Info "Packaging with electron-builder ($Target)…"
Invoke-Expression "npx electron-builder $builderArgs"

# ── 7. Report ─────────────────────────────────────────────────────────────────
Write-Host ""
Write-Ok "Build complete!  Artifacts in electron-app\dist\"
Write-Host ""
$distDir = Join-Path $ElectronDir 'dist'
Get-ChildItem $distDir -File |
    Where-Object { $_.Extension -in '.exe', '.dmg', '.AppImage', '.deb' } |
    ForEach-Object {
        $sz = [math]::Round($_.Length / 1MB, 1)
        Write-Host "    • $($_.Name)  ($sz MB)" -ForegroundColor Green
    }
Write-Host ""

Pop-Location
