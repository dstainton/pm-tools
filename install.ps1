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
# pipx install returns non-zero when the package is already present. The
# script handles that itself. PowerShell 7 would otherwise stop the script.
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

function Refresh-Path {
    $user = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $machine = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $env:Path = "$user;$machine"
}

function Get-PipxBinDir {
    $value = & pipx environment --value PIPX_BIN_DIR 2>$null
    if ($LASTEXITCODE -eq 0 -and $value) {
        return ($value | Select-Object -Last 1).ToString().Trim()
    }
    $text = & pipx environment 2>$null | Out-String
    $found = [regex]::Matches($text, "PIPX_BIN_DIR\s*[=:]\s*(.+)")
    if ($found.Count -gt 0) {
        return $found[$found.Count - 1].Groups[1].Value.Trim()
    }
    throw "Could not find pipx's bin directory. Run: pipx environment"
}

function Remove-OldPmHelper {
    param([string]$PipxPm)

    # The old pm-helper package installs pm.exe into Python's Scripts folder.
    # That folder is ahead of pipx on PATH, so `pm` stays the old command
    # after pipx has installed the new one. Uninstall the package, then
    # delete a Scripts\pm.exe that pip left behind.
    & python -m pip uninstall -y pm-helper | Out-Host

    $pipxFull = [System.IO.Path]::GetFullPath($PipxPm)
    $candidates = @()
    $where = & where.exe pm 2>$null
    if ($where) { $candidates += $where }
    $cmd = Get-Command pm -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { $candidates += $cmd.Source }

    $shadowed = $false
    foreach ($path in ($candidates | Select-Object -Unique)) {
        if (-not $path) { continue }
        $full = [System.IO.Path]::GetFullPath($path.ToString().Trim())
        if ([string]::Equals($full, $pipxFull, [System.StringComparison]::OrdinalIgnoreCase)) {
            continue
        }
        $dirName = [System.IO.Path]::GetFileName([System.IO.Path]::GetDirectoryName($full))
        $inPythonScripts = ($dirName -eq "Scripts") -and ($full -match '\\Python[^\\]*\\Scripts\\pm\.exe$')
        if ($inPythonScripts -and (Test-Path -LiteralPath $full)) {
            Remove-Item -LiteralPath $full -Force
            Write-Host "Removed leftover command: $full"
            $shadowed = $true
            continue
        }
        Write-Host "Another pm is ahead of the one just installed:"
        Write-Host "  $full"
        Write-Host "Remove that command and open a new PowerShell. Until then, run:"
        Write-Host "  $pipxFull"
        $shadowed = $true
    }
    if ($shadowed) {
        Write-Host "Open a new PowerShell window before running pm."
    }
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
    # `pipx upgrade` leaves the old files in place when the version number
    # does not change. Reinstall so the git tip is what actually runs.
    Write-Host "pm-tools is already installed. Reinstalling it from $source."
    & pipx install --force $source
    if ($LASTEXITCODE -ne 0) {
        throw "pipx could not install pm-tools."
    }
}

Refresh-Path
$bin = Get-PipxBinDir
$pmExe = Join-Path $bin "pm.exe"
if (-not (Test-Path -LiteralPath $pmExe)) {
    throw "pipx installed pm-tools but $pmExe is missing."
}

$helpText = & $pmExe -h 2>&1 | Out-String
if ($helpText -notmatch "doctor" -or $helpText -notmatch "pm-tools") {
    throw "The command at $pmExe is not the current pm-tools.`n$helpText"
}

Remove-OldPmHelper -PipxPm $pmExe

$config = Join-Path $env:USERPROFILE ".pm-tools\config.yaml"
if (-not (Test-Path $config)) {
    & $pmExe init
    if ($LASTEXITCODE -ne 0) {
        throw "pm init failed. The command that ran was: $pmExe"
    }
    if (-not (Test-Path $config)) {
        throw "pm init did not create $config. An older pm writes $env:USERPROFILE\.pm\config.yaml instead."
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
