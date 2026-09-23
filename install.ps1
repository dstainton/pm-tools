# First install of pm-tools on Windows.
# Requires Python 3.9+. Does not download a model and does not clone the repo.
#
#   irm https://raw.githubusercontent.com/dstainton/pm-tools/main/install.ps1 | iex
#
# From a checkout, to install that checkout instead of GitHub:
#   .\install.ps1 -FromPath

param(
    [switch]$FromPath
)

$ErrorActionPreference = "Stop"

function Refresh-Path {
    $user = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $machine = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $env:Path = "$user;$machine"
}

Write-Host "pm-tools install" -ForegroundColor Green

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw "Python 3.9 or newer is required. Install it, reopen PowerShell, and run this again."
}

$versionText = & python -c "import sys; print('%s.%s' % (sys.version_info[0], sys.version_info[1]))"
$parts = $versionText.Trim().Split(".")
$major = [int]$parts[0]
$minor = [int]$parts[1]
if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 9)) {
    throw "Python $versionText is too old. pm-tools needs Python 3.9 or newer."
}
Write-Host "Python $versionText"

$pipx = Get-Command pipx -ErrorAction SilentlyContinue
if (-not $pipx) {
    Write-Host "Installing pipx for the current user..."
    & python -m pip install --user pipx
    if ($LASTEXITCODE -ne 0) {
        throw "Could not install pipx."
    }
    & python -m pipx ensurepath
    Refresh-Path
}

$source = "git+https://github.com/dstainton/pm-tools.git"
if ($FromPath) {
    $source = $PSScriptRoot
}

Write-Host "Installing pm-tools from $source"
& pipx install $source
if ($LASTEXITCODE -ne 0) {
    Refresh-Path
    $existing = Get-Command pm -ErrorAction SilentlyContinue
    if (-not $existing) {
        throw "pipx install failed and pm is not on PATH."
    }
    Write-Host "pm is already installed; leaving that install in place."
}

Refresh-Path
$pm = Get-Command pm -ErrorAction SilentlyContinue
if (-not $pm) {
    throw "pm was installed but is not on PATH. Open a new terminal and run: pm init"
}

$config = Join-Path $env:USERPROFILE ".pm-tools\config.yaml"
if (-not (Test-Path $config)) {
    & pm init
    if ($LASTEXITCODE -ne 0) {
        throw "pm init failed."
    }
}
else {
    Write-Host "Config already exists at $config"
    Write-Host "Left it untouched. Run 'pm update' to add new settings."
}

Write-Host ""
Write-Host "Next:"
Write-Host "  1. Open $config and fill in the Jira URL, email, API token, and project."
Write-Host "  2. Run: pm doctor"
Write-Host "  3. Run: pm today"
