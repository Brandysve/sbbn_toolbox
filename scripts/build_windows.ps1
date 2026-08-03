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
    $allowedNames = @("nuitka", "launcher")
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
$nuitkaRoot = Join-Path $buildRoot "nuitka"
$launcherRoot = Join-Path $buildRoot "launcher"
$runtimePathFile = Join-Path $buildRoot "runtime-dist.path"
New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null

Push-Location $repoRoot
try {
    Invoke-Checked "py.exe" @(
        "-3.12", "-c",
        "import platform,struct,sys; assert sys.version_info[:2] == (3,12); assert struct.calcsize('P') == 8; assert platform.machine().endswith('64')"
    )
    if (-not (Test-Path -LiteralPath (Join-Path $venvRoot "Scripts\python.exe"))) {
        Invoke-Checked "py.exe" @("-3.12", "-m", "venv", $venvRoot)
    }
    $python = Join-Path $venvRoot "Scripts\python.exe"
    Invoke-Checked $python @("-m", "pip", "install", "-r", "requirements.lock")
    Invoke-Checked $python @(
        "-m", "pip", "install", "-r", "packaging\requirements-windows.lock"
    )
    Invoke-Checked $python @("-m", "pip", "install", "--no-deps", "-e", ".")

    if (-not $SkipTests) {
        Invoke-Checked $python @("-m", "ruff", "check", ".")
        Invoke-Checked $python @("-m", "ruff", "format", "--check", ".")
        Invoke-Checked $python @("-m", "mypy", "src")
        $previousPlatform = $env:QT_QPA_PLATFORM
        $env:QT_QPA_PLATFORM = "offscreen"
        try {
            Invoke-Checked $python @("-m", "pytest", "-q")
        }
        finally {
            $env:QT_QPA_PLATFORM = $previousPlatform
        }
    }

    # Ces deux dossiers sont les seules sorties de compilation remplacées.
    # L'environnement dédié est conservé et réutilisé, y compris avec -Clean.
    Remove-ControlledDirectory -Path $nuitkaRoot -BuildRoot $buildRoot
    Remove-ControlledDirectory -Path $launcherRoot -BuildRoot $buildRoot
    Remove-Item -LiteralPath $runtimePathFile -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $nuitkaRoot, $launcherRoot | Out-Null

    $nuitkaArguments = @(
        "-m", "nuitka",
        "--mode=standalone",
        "--enable-plugin=pyside6",
        "--include-qt-plugins=platforms,styles,imageformats",
        "--windows-console-mode=disable",
        "--msvc=latest",
        "--deployment",
        "--output-dir=$nuitkaRoot",
        "--output-filename=SBBN-Toolbox-runtime.exe",
        "--company-name=SBBN",
        "--product-name=SBBN Toolbox",
        "--file-description=SBBN Toolbox",
        "--file-version=1.0.0.0",
        "--product-version=1.0.0.0",
        "--copyright=SBBN",
        "--include-data-file=src/sbbn_toolbox/ui/theme/stylesheet.qss=sbbn_toolbox/ui/theme/stylesheet.qss",
        "--nofollow-import-to=tests,pytest,pytestqt,mypy,ruff",
        "--report=$nuitkaRoot\compilation-report.xml",
        "packaging\windows_entrypoint.py"
    )

    $iconPath = Join-Path $repoRoot "assets\icons\sbbn-toolbox.ico"
    if (Test-Path -LiteralPath $iconPath) {
        try {
            Add-Type -AssemblyName System.Drawing
            $icon = New-Object System.Drawing.Icon($iconPath)
            $icon.Dispose()
            $nuitkaArguments += "--windows-icon-from-ico=$iconPath"
        }
        catch {
            Write-Warning "L’icône disponible n’est pas un ICO Windows valide ; elle est ignorée."
        }
    }
    else {
        Write-Warning "Aucune icône ICO SBBN valide n’est disponible ; aucun logo n’est inventé."
    }

    Invoke-Checked $python $nuitkaArguments
    $runtimeCandidates = @(
        Get-ChildItem -LiteralPath $nuitkaRoot -Directory -Filter "*.dist" |
            Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "SBBN-Toolbox-runtime.exe") }
    )
    if ($runtimeCandidates.Count -ne 1) {
        throw "Le dossier autonome Nuitka est introuvable ou ambigu."
    }
    [IO.File]::WriteAllText(
        $runtimePathFile,
        $runtimeCandidates[0].FullName,
        (New-Object Text.UTF8Encoding($false))
    )

    $launcherOutput = Join-Path $launcherRoot "SBBN-Toolbox.exe"
    $compilerOptions = "/optimize+ /platform:x64 /target:winexe"
    if (Test-Path -LiteralPath $iconPath) {
        try {
            $validatedIcon = New-Object System.Drawing.Icon($iconPath)
            $validatedIcon.Dispose()
            $compilerOptions += " /win32icon:`"$iconPath`""
        }
        catch { }
    }
    $launcherCompilation = @{
        Path = (Join-Path $repoRoot "packaging\launcher.cs")
        OutputAssembly = $launcherOutput
        OutputType = "WindowsApplication"
        CompilerOptions = $compilerOptions
    }
    Add-Type @launcherCompilation
    if (-not (Test-Path -LiteralPath $launcherOutput)) {
        throw "La compilation du lanceur portable a échoué."
    }

    Write-Host "Compilation Windows terminée. Runtime : $($runtimeCandidates[0].FullName)"
}
finally {
    Pop-Location
}
