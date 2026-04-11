# ─────────────────────────────────────────────────────────────────────────────
# build-icons.ps1  —  Generate electron-app\resources\icon.{png,ico}
#                     from a high-res source PNG (1024×1024 recommended).
#
# Requires: ImageMagick  (winget install ImageMagick.Q16  or  choco install imagemagick)
#
# Usage:
#   .\scripts\build-icons.ps1 C:\path\to\logo.png
# ─────────────────────────────────────────────────────────────────────────────
[CmdletBinding()]
param([Parameter(Mandatory)][string]$Source)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path $Source)) { Write-Error "File not found: $Source"; exit 1 }

$RootDir  = Split-Path -Parent $PSScriptRoot
$OutDir   = Join-Path $RootDir 'electron-app\resources'
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$magick = Get-Command magick -ErrorAction SilentlyContinue
if (-not $magick) {
    Write-Error "ImageMagick 'magick' not found.`n  Install: winget install ImageMagick.Q16"
    exit 1
}

Write-Host "Source : $Source"
Write-Host "Output : $OutDir"
Write-Host ""

# ── icon.png (1024×1024) ─────────────────────────────────────────────────────
Write-Host "▸ Generating icon.png…"
& magick $Source -resize '1024x1024!' "$OutDir\icon.png"
Write-Host "  ✔ icon.png"

# ── icon.ico (multi-resolution) ──────────────────────────────────────────────
Write-Host "▸ Generating icon.ico…"
$sizes = @(16, 24, 32, 48, 64, 128, 256)
$tmpFiles = $sizes | ForEach-Object {
    $t = "$OutDir\.tmp_${_}.png"
    & magick $Source -resize "${_}x${_}!" $t
    $t
}
& magick @tmpFiles "$OutDir\icon.ico"
$tmpFiles | ForEach-Object { Remove-Item $_ -ErrorAction SilentlyContinue }
Write-Host "  ✔ icon.ico"

Write-Host ""
Write-Host "  ! icon.icns (macOS) must be generated on a Mac."
Write-Host "    Run:  ./scripts/build-icons.sh $Source  on your Mac build machine."
Write-Host ""
Write-Host "Icons written to electron-app\resources\"
Get-ChildItem $OutDir -File | Where-Object { $_.Extension -in '.png','.ico','.icns' } |
    ForEach-Object { Write-Host "  $($_.Name)  ($([math]::Round($_.Length/1KB,1)) KB)" }
