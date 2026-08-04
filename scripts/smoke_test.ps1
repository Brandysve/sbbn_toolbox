[CmdletBinding()]
param(
    [string]$ZipPath
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw "Ce smoke test doit être exécuté sous Windows."
}
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $ZipPath) {
    $ZipPath = Join-Path $repoRoot "artifacts\SBBN-Toolbox-Windows-x64.zip"
}
$ZipPath = (Resolve-Path -LiteralPath $ZipPath).Path
$checksumPath = "$ZipPath.sha256"
if (-not (Test-Path -LiteralPath $checksumPath)) {
    throw "Le fichier SHA-256 est absent."
}
$expectedHash = ([IO.File]::ReadAllText($checksumPath).Trim() -split "\s+")[0]
$actualHash = (Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $expectedHash.ToLowerInvariant()) {
    throw "Le checksum SHA-256 ne correspond pas au ZIP."
}

$smokeParent = Join-Path $repoRoot ".build\smoke"
New-Item -ItemType Directory -Force -Path $smokeParent | Out-Null
$smokeRoot = Join-Path $smokeParent ([Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $smokeRoot | Out-Null
try {
    Expand-Archive -LiteralPath $ZipPath -DestinationPath $smokeRoot
    $portableRoot = Join-Path $smokeRoot "SBBN-Toolbox"
    $executable = Join-Path $portableRoot "SBBN-Toolbox.exe"
    $runtimeDirectory = Join-Path $portableRoot "runtime"
    foreach ($required in @($executable, $runtimeDirectory, (Join-Path $portableRoot "config.json"), (Join-Path $portableRoot "README.txt"))) {
        if (-not (Test-Path -LiteralPath $required)) {
            throw "Fichier portable requis absent : $required"
        }
    }
    if (Test-Path -LiteralPath (Join-Path $portableRoot "data")) {
        throw "Le ZIP ne doit pas contenir de dossier data préexistant."
    }
    $filesBefore = @(
        Get-ChildItem -LiteralPath $portableRoot -Recurse -File |
            ForEach-Object { $_.FullName.Substring($portableRoot.Length) }
    )

    $previousPath = $env:PATH
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    try {
        $process = Start-Process -FilePath $executable -ArgumentList "--smoke-test" -WorkingDirectory $portableRoot -PassThru
        $deadline = [DateTime]::UtcNow.AddSeconds(30)
        $networkObserved = $false
        while (-not $process.HasExited -and [DateTime]::UtcNow -lt $deadline) {
            if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
                $applicationProcesses = @(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq $executable })
                foreach ($applicationProcess in $applicationProcesses) {
                    if (Get-NetTCPConnection -OwningProcess $applicationProcess.ProcessId -ErrorAction SilentlyContinue) {
                        $networkObserved = $true
                    }
                }
            }
            Start-Sleep -Milliseconds 50
            $process.Refresh()
        }
        if (-not $process.HasExited) {
            $process.Kill()
            throw "L’application compilée ne s’est pas fermée proprement dans le délai prévu."
        }
        if ($process.ExitCode -ne 0) {
            throw "L’application compilée a retourné le code $($process.ExitCode)."
        }
        if ($networkObserved) {
            throw "Une connexion réseau a été observée pendant le smoke test."
        }
    }
    finally {
        $env:PATH = $previousPath
    }

    $dataPath = Join-Path $portableRoot "data"
    foreach ($requiredData in @(
        (Join-Path $dataPath "settings.json"),
        (Join-Path $dataPath "logs\sbbn-toolbox.log")
    )) {
        if (-not (Test-Path -LiteralPath $requiredData)) {
            throw "Le premier lancement n’a pas créé : $requiredData"
        }
    }
    $documentResidues = @(
        Get-ChildItem -LiteralPath $dataPath -Recurse -File |
            Where-Object { $_.Extension -in @(".pdf", ".jpg", ".jpeg", ".png", ".bmp") }
    )
    if ($documentResidues.Count -gt 0) {
        throw "Un document utilisateur a été écrit dans data."
    }
    $filesAfter = @(
        Get-ChildItem -LiteralPath $portableRoot -Recurse -File |
            ForEach-Object { $_.FullName.Substring($portableRoot.Length) }
    )
    $unexpected = @(
        Compare-Object $filesBefore $filesAfter |
            Where-Object { $_.SideIndicator -eq "=>" -and $_.InputObject -notlike "\data\*" }
    )
    if ($unexpected.Count -gt 0) {
        throw "Écriture inattendue dans le dossier du programme : $($unexpected.InputObject -join ', ')"
    }
    Write-Host "Smoke test Windows réussi sans Python système, document résiduel ni connexion réseau."
}
finally {
    $resolvedSmoke = (Resolve-Path -LiteralPath $smokeRoot).Path
    $resolvedParent = (Resolve-Path -LiteralPath $smokeParent).Path
    if (-not $resolvedSmoke.StartsWith($resolvedParent + [IO.Path]::DirectorySeparatorChar)) {
        throw "Refus de nettoyer un dossier de smoke test non contrôlé."
    }
    Remove-Item -LiteralPath $resolvedSmoke -Recurse -Force
}
