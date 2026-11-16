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

function Protect-PrivateFile([string]$Path, [string]$Rights = "Read,Write") {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl = Get-Acl -LiteralPath $Path
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($rule in @($acl.Access)) {
        [void]$acl.RemoveAccessRule($rule)
    }
    $access = New-Object System.Security.AccessControl.FileSystemAccessRule(
        $identity, $Rights, "Allow"
    )
    [void]$acl.AddAccessRule($access)
    try {
        Set-Acl -LiteralPath $Path -AclObject $acl
    } catch {
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

function Stage-Bridge([string]$Root) {
    $bridge = Join-Path $Root "spark_image_tools.py"
    if (Test-Path -LiteralPath $bridge -PathType Leaf) {
        return
    }
    $sourceRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $sourceBridge = Join-Path $sourceRoot "client\spark_image_tools.py"
    $sourceJournal = Join-Path $sourceRoot "client\request_journal.py"
    if (-not (Test-Path -LiteralPath $sourceBridge -PathType Leaf)) {
        throw "Missing spark_image_tools.py in the Windows package"
    }
    Copy-Item -LiteralPath $sourceBridge -Destination $bridge
    $journal = Join-Path $Root "request_journal.py"
    if (-not (Test-Path -LiteralPath $journal -PathType Leaf) -and
        (Test-Path -LiteralPath $sourceJournal -PathType Leaf)) {
        Copy-Item -LiteralPath $sourceJournal -Destination $journal
    }
}

$Root = [System.IO.Path]::GetFullPath($InstallDir)
$venv = Join-Path $Root ".venv"
$python = Join-Path $venv "Scripts\python.exe"
$requirements = Join-Path $Root "requirements.txt"
if (-not (Test-Path -LiteralPath $requirements -PathType Leaf)) {
    $requirements = Join-Path $Root "client\image-tools-requirements.txt"
}

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
Stage-Bridge $Root
if (-not (Test-Path -LiteralPath $requirements -PathType Leaf)) {
    throw "Missing image client requirements manifest in installation directory"
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
Protect-PrivateFile $ApiKeyFile "Read"
Write-Output "Windows image client $Action complete: $Root"
