[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallDir,
    [ValidateSet("Install", "Update", "Uninstall")]
    [string]$Action = "Install",
    [string]$ConfigFile,
    [string]$ApiKeyFile
)

$ErrorActionPreference = "Stop"

function Assert-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

function Protect-PrivateFile([string]$Path) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }
    $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls.exe $Path /inheritance:r /grant:r "${user}:(R,W)" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not restrict private file permissions: $Path"
    }
}

function Backup-ExistingConfig([string]$Path) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backup = "$Path.bak.$stamp"
    Copy-Item -LiteralPath $Path -Destination $backup -Force
    Protect-PrivateFile $backup
}

$Root = [System.IO.Path]::GetFullPath($InstallDir)
$venv = Join-Path $Root ".venv"
$python = Join-Path $venv "Scripts\python.exe"
$requirements = Join-Path $Root "requirements.txt"

if ($Action -eq "Uninstall") {
    if (Test-Path -LiteralPath $venv) {
        Remove-Item -LiteralPath $venv -Recurse -Force
    }
    # Personal config, key, request journal, logs and output images are kept.
    exit 0
}

Assert-Command "py"
if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
    New-Item -ItemType Directory -Path $Root -Force | Out-Null
}
if (-not (Test-Path -LiteralPath $requirements -PathType Leaf)) {
    throw "Missing requirements.txt in installation directory"
}

& py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.11+ required"
}
if ($Action -eq "Update") {
    Backup-ExistingConfig $ConfigFile
}
& py -3 -m venv $venv
if ($LASTEXITCODE -ne 0) {
    throw "venv creation failed"
}
& $python -m pip install -r $requirements
if ($LASTEXITCODE -ne 0) {
    throw "dependency installation failed"
}

Protect-PrivateFile $ConfigFile
Protect-PrivateFile $ApiKeyFile
Write-Output "Windows image client $Action complete: $Root"
