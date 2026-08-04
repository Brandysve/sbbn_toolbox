[CmdletBinding()]
param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "La commande '$Command' a échoué avec le code $LASTEXITCODE."
    }
}

function Remove-ControlledDirectory {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$BuildRoot
    )
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $resolvedPath = (Resolve-Path -LiteralPath $Path).Path
    $resolvedRoot = (Resolve-Path -LiteralPath $BuildRoot).Path
    $allowedNames = @("pyinstaller")
    if (-not $resolvedPath.StartsWith($resolvedRoot + [IO.Path]::DirectorySeparatorChar) -or
        (Split-Path -Leaf $resolvedPath) -notin $allowedNames) {
        throw "Refus de nettoyer un dossier non contrôlé : $resolvedPath"
    }
    Remove-Item -LiteralPath $resolvedPath -Recurse -Force
}

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw "Ce script doit être exécuté sous Windows, jamais depuis WSL ou Linux."
}
if (-not [Environment]::Is64BitOperatingSystem -or -not [Environment]::Is64BitProcess) {
    throw "Windows et PowerShell doivent fonctionner en architecture x64."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$buildRoot = Join-Path $repoRoot ".build\windows"
$venvRoot = Join-Path $buildRoot "venv"
$pyinstallerRoot = Join-Path $buildRoot "pyinstaller"
$distRoot = Join-Path $pyinstallerRoot "dist"
$workRoot = Join-Path $pyinstallerRoot "work"
$distPathFile = Join-Path $buildRoot "pyinstaller-dist.path"
$requirementsPath = Join-Path $repoRoot "requirements.lock"
$windowsRequirementsPath = Join-Path $repoRoot "packaging\requirements-windows.lock"
$resourceManifestPath = Join-Path $repoRoot "packaging\pyinstaller_resources.json"
$entrypointPath = Join-Path $repoRoot "packaging\windows_entrypoint.py"
$versionInfoPath = Join-Path $repoRoot "packaging\windows_version_info.txt"
New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null

Invoke-Checked "py.exe" @(
    "-3.12", "-c",
    "import platform,struct,sys; assert sys.version_info[:2] == (3,12); assert struct.calcsize('P') == 8; assert platform.machine().endswith('64')"
)
if (-not (Test-Path -LiteralPath (Join-Path $venvRoot "Scripts\python.exe"))) {
    Invoke-Checked "py.exe" @("-3.12", "-m", "venv", $venvRoot)
}
$python = Join-Path $venvRoot "Scripts\python.exe"
Invoke-Checked $python @("-m", "pip", "install", "-r", $requirementsPath)
Invoke-Checked $python @("-m", "pip", "install", "-r", $windowsRequirementsPath)
Invoke-Checked $python @("-m", "pip", "install", "--no-deps", "-e", $repoRoot)

if (-not $SkipTests) {
    Invoke-Checked $python @("-m", "ruff", "check", $repoRoot)
    Invoke-Checked $python @("-m", "ruff", "format", "--check", $repoRoot)
    Invoke-Checked $python @("-m", "mypy", (Join-Path $repoRoot "src"))
    Invoke-Checked $python @("-m", "pytest", "-q", $repoRoot)
}

# Ce dossier est la seule sortie de packaging remplacée. L'environnement
# dédié est conservé et réutilisé entre les builds.
Remove-ControlledDirectory -Path $pyinstallerRoot -BuildRoot $buildRoot
Remove-Item -LiteralPath $distPathFile -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $pyinstallerRoot | Out-Null

$pyinstallerArguments = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onedir",
    "--windowed",
    "--name=SBBN-Toolbox",
    "--contents-directory=runtime",
    "--version-file=$versionInfoPath",
    "--distpath=$distRoot",
    "--workpath=$workRoot",
    "--specpath=$pyinstallerRoot",
    "--hidden-import=fitz",
    "--hidden-import=pymupdf",
    "--hidden-import=pypdf",
    "--hidden-import=img2pdf",
    "--hidden-import=PIL",
    "--exclude-module=pytest",
    "--exclude-module=pytestqt",
    "--exclude-module=mypy",
    "--exclude-module=ruff"
)

$resourceManifest = Get-Content -LiteralPath $resourceManifestPath -Raw | ConvertFrom-Json
foreach ($resource in $resourceManifest.data) {
    $sourcePath = [IO.Path]::GetFullPath((Join-Path $repoRoot $resource.source))
    if (-not $sourcePath.StartsWith($repoRoot + [IO.Path]::DirectorySeparatorChar) -or
        -not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
        throw "Ressource PyInstaller absente ou hors dépôt : $sourcePath"
    }
    $pyinstallerArguments += "--add-data=$sourcePath;$($resource.destination)"
}

$iconPath = Join-Path $repoRoot "assets\icons\sbbn-toolbox.ico"
if (Test-Path -LiteralPath $iconPath) {
    try {
        Add-Type -AssemblyName System.Drawing
        $icon = New-Object System.Drawing.Icon($iconPath)
        $icon.Dispose()
        $pyinstallerArguments += "--icon=$iconPath"
    }
    catch {
        Write-Warning "L’icône disponible n’est pas un ICO Windows valide ; elle est ignorée."
    }
}
else {
    Write-Warning "Aucune icône ICO SBBN valide n’est disponible ; aucun logo n’est inventé."
}

Invoke-Checked $python ($pyinstallerArguments + $entrypointPath)
$applicationDist = Join-Path $distRoot "SBBN-Toolbox"
if (-not (Test-Path -LiteralPath (Join-Path $applicationDist "SBBN-Toolbox.exe")) -or
    -not (Test-Path -LiteralPath (Join-Path $applicationDist "runtime"))) {
    throw "Le dossier onedir PyInstaller est incomplet."
}
[IO.File]::WriteAllText(
    $distPathFile,
    $applicationDist,
    (New-Object Text.UTF8Encoding($false))
)
Write-Host "Packaging Windows PyInstaller terminé : $applicationDist"
