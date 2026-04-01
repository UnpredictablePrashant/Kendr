#Requires -Version 5.1
# kendr install script — Windows (PowerShell)
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
#   powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -Full
#
param([switch]$Full)

$ErrorActionPreference = 'Stop'
$KendrVersion = '0.2.0'

function Write-Banner  { Write-Host "`n  ⚡ kendr v$KendrVersion installer`n" -ForegroundColor Cyan }
function Write-Info    { param([string]$Msg) Write-Host "  ▸ $Msg" -ForegroundColor Cyan }
function Write-Ok      { param([string]$Msg) Write-Host "  ✔ $Msg" -ForegroundColor Green }
function Write-Warn    { param([string]$Msg) Write-Host "  ⚠ $Msg" -ForegroundColor Yellow }
function Write-Fail    { param([string]$Msg) Write-Host "`n  ✘ ERROR: $Msg`n" -ForegroundColor Red; exit 1 }

function Find-Python {
    foreach ($cmd in @('py', 'python', 'python3')) {
        if (Get-Command $cmd -ErrorAction SilentlyContinue) { return $cmd }
    }
    return $null
}

Write-Banner

# ── 1. Python check ──────────────────────────────────────────────────────────
$PyCmd = Find-Python
if (-not $PyCmd) {
    Write-Fail "Python 3.10+ is required but was not found.`n  Install from https://python.org/downloads`n  (check 'Add Python to PATH' during install)"
}

$PyVer = & $PyCmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
$Parts = $PyVer -split '\.'
if ([int]$Parts[0] -lt 3 -or ([int]$Parts[0] -eq 3 -and [int]$Parts[1] -lt 10)) {
    Write-Fail "Python 3.10+ is required. Found: Python $PyVer`n  Install a newer version from https://python.org/downloads"
}
Write-Ok "Python $PyVer detected"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $RepoRoot

# ── 2. Virtual environment ───────────────────────────────────────────────────
$VenvPython  = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$VenvScripts = Join-Path $RepoRoot '.venv\Scripts'
$VenvPip     = Join-Path $RepoRoot '.venv\Scripts\pip.exe'

if (-not (Test-Path '.venv')) {
    Write-Info "Creating virtual environment..."
    if ($PyCmd -eq 'py') { py -3 -m venv .venv } else { & $PyCmd -m venv .venv }
} elseif (-not (Test-Path $VenvPython)) {
    Write-Info "Recreating virtual environment (wrong platform venv detected)..."
    Remove-Item -Recurse -Force .venv
    if ($PyCmd -eq 'py') { py -3 -m venv .venv } else { & $PyCmd -m venv .venv }
}
Write-Ok "Virtual environment ready"

# ── 3. Upgrade pip ───────────────────────────────────────────────────────────
Write-Info "Upgrading pip..."
& $VenvPython -m pip install --upgrade pip --quiet
Write-Ok "pip up to date"

# ── 4. Install kendr ─────────────────────────────────────────────────────────
if ($Full) {
    Write-Info "Installing kendr with all optional providers..."
    & $VenvPip install -e ".[full]" --quiet
    Write-Ok "kendr installed (full — all providers)"
} else {
    Write-Info "Installing kendr (core + OpenAI)..."
    & $VenvPip install -e "." --quiet
    Write-Ok "kendr installed"
    Write-Host ""
    Write-Host "  Add more LLM providers any time:" -ForegroundColor Yellow
    Write-Host "    $VenvPip install 'kendr-runtime[anthropic]'  -- Anthropic Claude" -ForegroundColor Cyan
    Write-Host "    $VenvPip install 'kendr-runtime[google]'     -- Google Gemini" -ForegroundColor Cyan
    Write-Host "    $VenvPip install 'kendr-runtime[ollama]'     -- Local Ollama" -ForegroundColor Cyan
    Write-Host "    $VenvPip install 'kendr-runtime[full]'       -- All of the above" -ForegroundColor Cyan
}

# ── 5. Bootstrap runtime state ───────────────────────────────────────────────
$BootstrapScript = Join-Path $RepoRoot 'scripts\bootstrap_local_state.py'
if (Test-Path $BootstrapScript) {
    Write-Info "Bootstrapping runtime state..."
    try {
        & $VenvPython $BootstrapScript 2>$null
        Write-Ok "Runtime state ready"
    } catch {
        Write-Warn "Bootstrap skipped (non-fatal)"
    }
}

# ── 6. Add Scripts dir to User PATH ─────────────────────────────────────────
$UserPath  = [Environment]::GetEnvironmentVariable('Path', 'User') ?? ''
$PathParts = $UserPath -split ';' | Where-Object { $_ -ne '' }
if ($PathParts -notcontains $VenvScripts) {
    $NewPath = ($PathParts + $VenvScripts) -join ';'
    [Environment]::SetEnvironmentVariable('Path', $NewPath, 'User')
    Write-Ok "Added kendr to User PATH"
} else {
    Write-Ok "PATH already configured"
}

if (($env:Path -split ';') -notcontains $VenvScripts) {
    $env:Path = "$VenvScripts;$env:Path"
}

# ── 7. Done ──────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ✔ kendr v$KendrVersion is ready!" -ForegroundColor Green
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor White
Write-Host "  1. Open a new terminal (to pick up PATH changes)"
Write-Host "  2. Set your API key:     kendr setup set openai OPENAI_API_KEY sk-..." -ForegroundColor Cyan
Write-Host "  3. Set your working dir: kendr setup set core_runtime KENDR_WORKING_DIR C:\kendr-work" -ForegroundColor Cyan
Write-Host "  4. Launch the Web UI:    kendr ui" -ForegroundColor Cyan
Write-Host "     Or run a CLI query:   kendr run `"summarise the AI chip market`"" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Docs -> https://github.com/kendr-ai/kendr/blob/main/docs/quickstart.md" -ForegroundColor Cyan
Write-Host ""
