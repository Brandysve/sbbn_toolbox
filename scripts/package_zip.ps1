[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw "Ce script doit être exécuté sous Windows."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$buildRoot = Join-Path $repoRoot ".build\windows"
$runtimePathFile = Join-Path $buildRoot "runtime-dist.path"
$launcher = Join-Path $buildRoot "launcher\SBBN-Toolbox.exe"
$packageRoot = Join-Path $buildRoot "package"
$portableRoot = Join-Path $packageRoot "SBBN-Toolbox"
$runtimeTarget = Join-Path $portableRoot "runtime"
$artifactsRoot = Join-Path $repoRoot "artifacts"
$zipPath = Join-Path $artifactsRoot "SBBN-Toolbox-Windows-x64.zip"
$checksumPath = "$zipPath.sha256"
$readmeSource = Join-Path $repoRoot "packaging\README.txt"

if (-not (Test-Path -LiteralPath $runtimePathFile) -or
    -not (Test-Path -LiteralPath $launcher) -or
    -not (Test-Path -LiteralPath $readmeSource)) {
    throw "Exécutez d’abord scripts\build_windows.ps1."
}
$runtimeSource = [IO.File]::ReadAllText($runtimePathFile).Trim()
if (-not (Test-Path -LiteralPath $runtimeSource) -or
    -not (Test-Path -LiteralPath (Join-Path $runtimeSource "SBBN-Toolbox-runtime.exe"))) {
    throw "Le runtime Nuitka indiqué par le build est invalide."
}

if (Test-Path -LiteralPath $packageRoot) {
    $resolvedPackage = (Resolve-Path -LiteralPath $packageRoot).Path
    $resolvedBuild = (Resolve-Path -LiteralPath $buildRoot).Path
    if (-not $resolvedPackage.StartsWith($resolvedBuild + [IO.Path]::DirectorySeparatorChar) -or
        (Split-Path -Leaf $resolvedPackage) -ne "package") {
        throw "Refus de nettoyer un dossier de package non contrôlé."
    }
    Remove-Item -LiteralPath $resolvedPackage -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $runtimeTarget, $artifactsRoot | Out-Null
Copy-Item -LiteralPath $launcher -Destination (Join-Path $portableRoot "SBBN-Toolbox.exe")
Copy-Item -Path (Join-Path $runtimeSource "*") -Destination $runtimeTarget -Recurse
Copy-Item -LiteralPath $readmeSource -Destination (Join-Path $portableRoot "README.txt")
[IO.File]::WriteAllText(
    (Join-Path $portableRoot "config.json"),
    "{`n  `"schemaVersion`": 1,`n  `"dataPath`": `"data`"`n}`n",
    (New-Object Text.UTF8Encoding($false))
)

$forbidden = @(
    Get-ChildItem -LiteralPath $portableRoot -Recurse -File |
        Where-Object {
            $_.Extension -in @(".py", ".pyc", ".pyo", ".pytest", ".jpg", ".jpeg", ".png", ".bmp", ".pdf") -or
            $_.FullName -match "([\\/])(tests?|fixtures?|__pycache__|\.git)([\\/]|$)"
        }
)
if ($forbidden.Count -gt 0) {
    throw "Le package contient des sources, tests ou documents interdits : $($forbidden.FullName -join ', ')"
}
$topLevelNames = @(
    Get-ChildItem -LiteralPath $portableRoot | Select-Object -ExpandProperty Name | Sort-Object
)
$expectedNames = @("config.json", "README.txt", "runtime", "SBBN-Toolbox.exe") | Sort-Object
if (($topLevelNames -join "|") -ne ($expectedNames -join "|")) {
    throw "La racine portable ne correspond pas à la structure attendue."
}

Remove-Item -LiteralPath $zipPath, $checksumPath -Force -ErrorAction SilentlyContinue
Compress-Archive -LiteralPath $portableRoot -DestinationPath $zipPath -CompressionLevel Optimal
$hash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText(
    $checksumPath,
    "$hash  SBBN-Toolbox-Windows-x64.zip`n",
    (New-Object Text.UTF8Encoding($false))
)

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::OpenRead($zipPath)
try {
    $entries = @($archive.Entries | ForEach-Object { $_.FullName })
    if (-not ($entries -contains "SBBN-Toolbox/SBBN-Toolbox.exe") -or
        -not ($entries -contains "SBBN-Toolbox/config.json") -or
        -not ($entries -contains "SBBN-Toolbox/README.txt") -or
        -not ($entries | Where-Object { $_ -like "SBBN-Toolbox/runtime/*" })) {
        throw "Le contenu exact du ZIP est incomplet."
    }
    if ($entries | Where-Object { $_ -match "\.(py|pyc|jpg|jpeg|png|bmp|pdf)$" }) {
        throw "Le ZIP contient un fichier interdit."
    }
}
finally {
    $archive.Dispose()
}

$expandedBytes = (
    Get-ChildItem -LiteralPath $portableRoot -Recurse -File |
        Measure-Object -Property Length -Sum
).Sum
$zipBytes = (Get-Item -LiteralPath $zipPath).Length
$report = [ordered]@{
    archive = $zipPath
    sha256 = $hash
    compressedBytes = $zipBytes
    expandedBytes = $expandedBytes
    fileCount = @(Get-ChildItem -LiteralPath $portableRoot -Recurse -File).Count
}
$report | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $artifactsRoot "package-report.json") -Encoding UTF8
Write-Host "Archive : $zipPath"
Write-Host "SHA-256 : $hash"
Write-Host "Taille ZIP : $zipBytes octets ; taille décompressée : $expandedBytes octets"
