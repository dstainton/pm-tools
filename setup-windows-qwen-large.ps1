<#
.SYNOPSIS
Set up pm-helper and a local Qwen3.8-27B OpenAI-compatible server on Windows.

.DESCRIPTION
This script is intended for a Windows x64 AMD Ryzen AI laptop.

It:
  - verifies Python
  - installs pm-helper in editable mode when pyproject.toml is present
  - downloads the latest official llama.cpp Windows x64 Vulkan build
  - verifies llama.cpp devices
  - downloads Qwen3.8-27B Q4_K_M unless skipped
  - optionally starts llama-server on 127.0.0.1

It does NOT modify AMD drivers, BIOS/VGM settings, Windows firewall rules,
execution policy outside the current shell, or system-wide environment
variables.
#>

[CmdletBinding()]
param(
    [switch]$SkipModelDownload,
    [switch]$StartServer,
    [int]$ContextSize = 8192,
    [ValidateRange(1, 12)]
    [int]$Threads = 6,
    [ValidateRange(0, 999)]
    [int]$GpuLayers = 0,
    [ValidateRange(1, 65535)]
    [int]$Port = 8080
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ModelRef = "ggml-org/Qwen3.8-27B-GGUF:Q4_K_M"
$ModelAlias = "qwen-local"

$PmHome = Join-Path $HOME ".pm"
$LlamaDir = Join-Path $PmHome "llama.cpp"
$DownloadDir = Join-Path $PmHome "downloads"
$ModelDir = Join-Path $PmHome "models"
$ModelFile = "Qwen3.8-27B-Q4_K_M.gguf"
$ModelPath = Join-Path $ModelDir $ModelFile
$ModelUrl = "https://huggingface.co/ggml-org/Qwen3.8-27B-GGUF/resolve/main/Qwen3.8-27B-Q4_K_M.gguf?download=true"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Require-Command {
    param(
        [Parameter(Mandatory)]
        [string]$Name,
        [string]$HelpMessage
    )

    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        if ($HelpMessage) {
            throw "$Name was not found. $HelpMessage"
        }
        throw "$Name was not found."
    }
    return $cmd
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory)]
        [string]$FilePath,
        [Parameter(ValueFromRemainingArguments)]
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE`: $FilePath $($Arguments -join ' ')"
    }
}

Write-Host "pm-helper local Qwen setup" -ForegroundColor Green
Write-Host "Model: $ModelRef"
Write-Host "Endpoint after start: http://127.0.0.1:$Port/v1"

Write-Step "Checking Windows and available memory"

if ($env:OS -ne "Windows_NT") {
    throw "This setup script is for Windows."
}

$computer = Get-CimInstance Win32_ComputerSystem
$ramGb = [math]::Round($computer.TotalPhysicalMemory / 1GB, 1)
Write-Host "Physical RAM: $ramGb GB"

if ($ramGb -lt 28) {
    Write-Warning "Qwen3.8-27B Q4_K_M is not recommended with less than about 32 GB of system RAM."
}

$video = Get-CimInstance Win32_VideoController |
    Select-Object Name, DriverVersion

Write-Host "Display adapter(s):"
$video | Format-Table -AutoSize

Write-Host ""
Write-Host "This script does not install or change display drivers."
Write-Host "Use the Lenovo/organizationally approved AMD driver with Vulkan support."

Write-Step "Checking Python"

$python = Require-Command "python" "Install an approved Python 3 release and ensure python.exe is on PATH."
Invoke-Checked $python.Source "--version"

Write-Step "Installing the Python application dependencies"

if (Test-Path (Join-Path (Get-Location) "pyproject.toml")) {
    Write-Host "Installing pm-helper from the current repository in editable mode..."
    Invoke-Checked $python.Source "-m" "pip" "install" "-e" "."
}
else {
    Write-Warning "No pyproject.toml found in the current directory. Skipping 'pip install -e .'."
    Write-Warning "Run this script from the pm_helper repository if you want it to install the CLI too."
}

Write-Step "Preparing local runtime directories"

New-Item -ItemType Directory -Path $PmHome -Force | Out-Null
New-Item -ItemType Directory -Path $LlamaDir -Force | Out-Null
New-Item -ItemType Directory -Path $DownloadDir -Force | Out-Null
New-Item -ItemType Directory -Path $ModelDir -Force | Out-Null

$systemDriveName = $env:SystemDrive.TrimEnd(":")
$drive = Get-PSDrive -Name $systemDriveName -ErrorAction SilentlyContinue
if ($drive) {
    $freeGb = [math]::Round($drive.Free / 1GB, 1)
    Write-Host "Free space on $($env:SystemDrive): $freeGb GB"
    if ($freeGb -lt 25 -and -not $SkipModelDownload) {
        Write-Warning "Less than 25 GB is free. The Qwen model download may not fit comfortably."
    }
}

Write-Step "Downloading the latest official llama.cpp Windows x64 Vulkan build"

$releaseApi = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
$headers = @{
    "User-Agent" = "pm-helper-qwen-setup"
}

try {
    $release = Invoke-RestMethod -Uri $releaseApi -Headers $headers
}
catch {
    throw "Could not query the latest llama.cpp release from GitHub. Check network/proxy access. $($_.Exception.Message)"
}

# Stable llama.cpp releases may contain only nightly-tag.txt and point to the
# current binary release. Prefer a direct Vulkan asset when present; otherwise
# follow that official pointer.
$binaryRelease = $release
$asset = $binaryRelease.assets |
    Where-Object { $_.name -match "bin-win-vulkan-x64\.zip$" } |
    Select-Object -First 1

if (-not $asset) {
    $nightlyPointer = $release.assets |
        Where-Object { $_.name -eq "nightly-tag.txt" } |
        Select-Object -First 1

    if ($nightlyPointer) {
        Write-Host "Stable release $($release.tag_name) points to a separate binary release."

        try {
            $nightlyTag = (
                Invoke-RestMethod `
                    -Uri $nightlyPointer.browser_download_url `
                    -Headers $headers
            ).ToString().Trim()
        }
        catch {
            throw "Could not read llama.cpp nightly-tag.txt. $($_.Exception.Message)"
        }

        if ([string]::IsNullOrWhiteSpace($nightlyTag)) {
            throw "llama.cpp nightly-tag.txt was empty."
        }

        Write-Host "Binary release tag: $nightlyTag"

        $nightlyReleaseApi = "https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/$nightlyTag"

        try {
            $binaryRelease = Invoke-RestMethod -Uri $nightlyReleaseApi -Headers $headers
        }
        catch {
            throw "Could not query llama.cpp binary release '$nightlyTag'. $($_.Exception.Message)"
        }

        $asset = $binaryRelease.assets |
            Where-Object { $_.name -match "bin-win-vulkan-x64\.zip$" } |
            Select-Object -First 1
    }
}

if (-not $asset) {
    $availableAssets = @($binaryRelease.assets | ForEach-Object { $_.name }) -join ", "
    throw "Could not find a Windows x64 Vulkan ZIP in llama.cpp release '$($binaryRelease.tag_name)'. Available assets: $availableAssets"
}

$zipPath = Join-Path $DownloadDir $asset.name
Write-Host "Stable release: $($release.tag_name)"
Write-Host "Binary release: $($binaryRelease.tag_name)"
Write-Host "Asset:          $($asset.name)"

if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}

Invoke-WebRequest `
    -Uri $asset.browser_download_url `
    -Headers $headers `
    -OutFile $zipPath

Write-Host "Replacing previous portable llama.cpp Vulkan runtime..."
if (Test-Path $LlamaDir) {
    Get-ChildItem $LlamaDir -Force | Remove-Item -Recurse -Force
}
Expand-Archive -Path $zipPath -DestinationPath $LlamaDir -Force
Remove-Item $zipPath -Force

$serverExe = Get-ChildItem $LlamaDir -Recurse -Filter "llama-server.exe" |
    Select-Object -First 1

$cliExe = Get-ChildItem $LlamaDir -Recurse -Filter "llama-cli.exe" |
    Select-Object -First 1

if (-not $serverExe) {
    throw "llama-server.exe was not found after extracting the Vulkan release."
}

Write-Host "llama-server: $($serverExe.FullName)"

Write-Step "Checking llama.cpp compute devices"

if ($cliExe) {
    & $cliExe.FullName "--list-devices"
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "llama-cli --list-devices returned an error. Vulkan acceleration may not be available."
    }
}
else {
    Write-Warning "llama-cli.exe was not found, so device enumeration was skipped."
}

if (-not $SkipModelDownload) {
    Write-Step "Downloading Qwen3.8-27B Q4_K_M"

    if (Test-Path $ModelPath) {
        $existingSizeGb = [math]::Round((Get-Item $ModelPath).Length / 1GB, 2)
        Write-Host "Existing model file found: $ModelPath ($existingSizeGb GB)"
        Write-Host "The download will resume if the file is incomplete."
    }

    $curl = Get-Command "curl.exe" -ErrorAction SilentlyContinue
    if ($curl) {
        & $curl.Source `
            "--fail" `
            "--location" `
            "--retry" "3" `
            "--retry-delay" "5" `
            "--continue-at" "-" `
            "--output" $ModelPath `
            $ModelUrl

        if ($LASTEXITCODE -ne 0) {
            throw "The Qwen model download failed with curl exit code $LASTEXITCODE."
        }
    }
    else {
        Write-Warning "curl.exe was not found. Falling back to Invoke-WebRequest without resume support."
        Invoke-WebRequest -Uri $ModelUrl -OutFile $ModelPath
    }

    $modelSizeGb = [math]::Round((Get-Item $ModelPath).Length / 1GB, 2)
    Write-Host "Model ready: $ModelPath ($modelSizeGb GB)"
}
else {
    Write-Host "Skipping model download by request."
    if (-not (Test-Path $ModelPath)) {
        Write-Warning "The model file is not present. Download it before starting the server:"
        Write-Warning "  $ModelUrl"
    }
}

$serverArgs = @(
    "-m", $ModelPath,
    "--alias", $ModelAlias,
    "--host", "127.0.0.1",
    "--port", "$Port",
    "--ctx-size", "$ContextSize",
    "--threads", "$Threads",
    "-ngl", "$GpuLayers"
)

Write-Step "Setup complete"

Write-Host "Local API base URL:"
Write-Host "  http://127.0.0.1:$Port/v1" -ForegroundColor Green
Write-Host ""
Write-Host "API model alias:"
Write-Host "  $ModelAlias" -ForegroundColor Green
Write-Host ""
Write-Host "Start command:"
Write-Host ('  & "{0}" {1}' -f $serverExe.FullName, ($serverArgs -join " "))

if ($StartServer) {
    if (-not (Test-Path $ModelPath)) {
        throw "Cannot start the server because the model file is missing: $ModelPath"
    }

    Write-Step "Starting Qwen server"
    Write-Host "Press Ctrl+C to stop it."
    Write-Host ""
    & $serverExe.FullName @serverArgs
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "To start it now, rerun:"
Write-Host "  .\setup-windows-qwen-large.ps1 -StartServer"
Write-Host ""
Write-Host "Then verify:"
Write-Host "  Invoke-RestMethod http://127.0.0.1:$Port/v1/models"
Write-Host ""
Write-Host "Ryzen AI 5 PRO 340 tuning:"
Write-Host "  Start with CPU-only (-GpuLayers 0). Then compare 8, 16, 24, and 99."
Write-Host "  Keep -Threads 6 unless benchmarking shows otherwise."
