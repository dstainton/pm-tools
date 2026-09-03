<#
.SYNOPSIS
Set up a small local Qwen model for pm-helper on Windows.

.DESCRIPTION
Installs or reuses llama.cpp, downloads Qwen3-4B Q4_K_M (~2.5 GB),
and optionally starts an OpenAI-compatible local server.

Designed for:
  AMD Ryzen AI 5 PRO 340
  Radeon 840M
  32 GB RAM
  Windows x64

The small model uses the same API model alias, "qwen-local", as the larger
27B setup so the Python CLI does not need to change when models are swapped.

This script is intentionally tether-friendly:
  - existing llama.cpp is reused
  - existing model files are reused
  - curl downloads resume if interrupted
  - no extra Python package download is required
#>

[CmdletBinding()]
param(
    [switch]$StartServer,
    [switch]$SkipModelDownload,
    [switch]$ForceRuntimeUpdate,
    [int]$ContextSize = 8192,
    [ValidateRange(1, 12)]
    [int]$Threads = 6,
    [ValidateRange(0, 999)]
    [int]$GpuLayers = 99,
    [ValidateRange(1, 65535)]
    [int]$Port = 8080
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ModelAlias = "qwen-local"
$ModelRepo = "ggml-org/Qwen3-4B-GGUF"
$ModelFile = "Qwen3-4B-Q4_K_M.gguf"
$ModelUrl = "https://huggingface.co/${ModelRepo}/resolve/main/${ModelFile}?download=true"

$PmHome = Join-Path $HOME ".pm"
$LlamaDir = Join-Path $PmHome "llama.cpp"
$ModelDir = Join-Path $PmHome "models"
$DownloadDir = Join-Path $PmHome "downloads"
$ModelPath = Join-Path $ModelDir $ModelFile

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

Write-Host "pm-helper small local Qwen setup" -ForegroundColor Green
Write-Host "Model:    $ModelRepo / $ModelFile"
Write-Host "Download: approximately 2.5 GB"
Write-Host "Endpoint: http://127.0.0.1:$Port/v1"
Write-Host "Alias:    $ModelAlias"

if ($env:OS -ne "Windows_NT") {
    throw "This setup script is for Windows."
}

New-Item -ItemType Directory -Path $PmHome -Force | Out-Null
New-Item -ItemType Directory -Path $LlamaDir -Force | Out-Null
New-Item -ItemType Directory -Path $ModelDir -Force | Out-Null
New-Item -ItemType Directory -Path $DownloadDir -Force | Out-Null

Write-Step "Checking Python"

$python = Require-Command "python" "Install an approved Python 3 release and ensure python.exe is on PATH."
& $python.Source "--version"
if ($LASTEXITCODE -ne 0) {
    throw "Python did not run successfully."
}

Write-Host "pm-helper talks to llama.cpp with its existing requests dependency; no OpenAI SDK is required."

Write-Step "Checking llama.cpp"

$serverExe = Get-ChildItem $LlamaDir -Recurse -Filter "llama-server.exe" -ErrorAction SilentlyContinue |
    Select-Object -First 1

if ($serverExe -and -not $ForceRuntimeUpdate) {
    Write-Host "Existing llama.cpp runtime found:"
    Write-Host "  $($serverExe.FullName)"
    Write-Host "Skipping runtime download. Use -ForceRuntimeUpdate to replace it."
}
else {
    Write-Host "Downloading the current official Windows x64 Vulkan build of llama.cpp..."

    $releaseApi = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
    $headers = @{
        "User-Agent" = "pm-helper-qwen-small-setup"
    }

    try {
        $release = Invoke-RestMethod -Uri $releaseApi -Headers $headers
    }
    catch {
        throw "Could not query the latest llama.cpp release from GitHub. Check network/proxy access. $($_.Exception.Message)"
    }

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

    Invoke-WebRequest `
        -Uri $asset.browser_download_url `
        -Headers $headers `
        -OutFile $zipPath

    Get-ChildItem $LlamaDir -Force | Remove-Item -Recurse -Force
    Expand-Archive -Path $zipPath -DestinationPath $LlamaDir -Force
    Remove-Item $zipPath -Force

    $serverExe = Get-ChildItem $LlamaDir -Recurse -Filter "llama-server.exe" |
        Select-Object -First 1

    if (-not $serverExe) {
        throw "llama-server.exe was not found after extracting the Vulkan release."
    }

    Write-Host "llama.cpp ready:"
    Write-Host "  $($serverExe.FullName)"
}

$cliExe = Get-ChildItem $LlamaDir -Recurse -Filter "llama-cli.exe" -ErrorAction SilentlyContinue |
    Select-Object -First 1

if ($cliExe) {
    Write-Step "Checking available llama.cpp devices"
    & $cliExe.FullName "--list-devices"
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Device enumeration returned an error. Vulkan acceleration may not be available."
    }
}

if (-not $SkipModelDownload) {
    Write-Step "Downloading Qwen3-4B Q4_K_M"

    if (Test-Path $ModelPath) {
        $existingSizeGb = [math]::Round((Get-Item $ModelPath).Length / 1GB, 2)
        Write-Host "Existing model file found: $ModelPath ($existingSizeGb GB)"
        Write-Host "curl will resume the download if the file is incomplete."
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
}

# Qwen3 thinks by default. pm's prompts are written for instruct mode, so
# the server turns thinking off. Same flags as the large Qwen3.8 script.
$serverArgs = @(
    "-m", $ModelPath,
    "--alias", $ModelAlias,
    "--host", "127.0.0.1",
    "--port", "$Port",
    "--ctx-size", "$ContextSize",
    "--threads", "$Threads",
    "-ngl", "$GpuLayers",
    "--jinja",
    "--reasoning-budget", "0"
)

Write-Step "Setup complete"

Write-Host "Model:       $ModelFile"
Write-Host "API model:   $ModelAlias"
Write-Host "API base:    http://127.0.0.1:$Port/v1"
Write-Host "Context:     $ContextSize"
Write-Host "CPU threads: $Threads"
Write-Host "GPU layers:  $GpuLayers"
Write-Host ""
Write-Host "The default -GpuLayers 99 attempts full Vulkan offload."
Write-Host "If the Radeon 840M is slower than the CPU, rerun with -GpuLayers 0."
Write-Host ""
Write-Host "Start command:"
Write-Host ('  & "{0}" {1}' -f $serverExe.FullName, ($serverArgs -join " "))

if ($StartServer) {
    if (-not (Test-Path $ModelPath)) {
        throw "Cannot start the server because the model file is missing: $ModelPath"
    }

    Write-Step "Starting Qwen3-4B"
    Write-Host "Press Ctrl+C to stop it."
    Write-Host ""
    & $serverExe.FullName @serverArgs
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "To start it now:"
Write-Host "  .\setup-windows-qwen-small.ps1 -StartServer"
Write-Host ""
Write-Host "To try CPU-only inference instead:"
Write-Host "  .\setup-windows-qwen-small.ps1 -StartServer -GpuLayers 0"
Write-Host ""
Write-Host "Verify the endpoint after the server starts:"
Write-Host "  Invoke-RestMethod http://127.0.0.1:$Port/v1/models"
