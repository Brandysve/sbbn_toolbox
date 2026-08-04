import ast
import json
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_windows_packaging_metadata_and_locked_compiler() -> None:
    metadata = json.loads(
        (REPOSITORY_ROOT / "packaging" / "version_info.json").read_text(encoding="utf-8")
    )
    build_lock = (REPOSITORY_ROOT / "packaging" / "requirements-windows.lock").read_text(
        encoding="utf-8"
    )

    assert metadata == {
        "productName": "SBBN Toolbox",
        "executableName": "SBBN-Toolbox.exe",
        "version": "1.0.0",
        "architecture": "Windows x64",
        "console": False,
        "requiresAdministrator": False,
    }
    assert "pyinstaller==6.16.0" in build_lock
    assert "pyinstaller-hooks-contrib==2025.8" in build_lock
    assert "nuitka" not in build_lock.lower()
    assert ">=" not in build_lock


def test_packaging_scripts_enforce_windows_and_expected_archive() -> None:
    scripts = {
        name: (REPOSITORY_ROOT / "scripts" / name).read_text(encoding="utf-8")
        for name in ("build_windows.ps1", "package_zip.ps1", "smoke_test.ps1")
    }

    assert all("Win32NT" in script for script in scripts.values())
    assert '$ErrorActionPreference = "Stop"' in scripts["build_windows.ps1"]
    assert (
        '$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot ".."))' in scripts["build_windows.ps1"]
    )
    for source_path in (
        "requirementsPath",
        "windowsRequirementsPath",
        "resourceManifestPath",
        "entrypointPath",
        "versionInfoPath",
    ):
        assert f"${source_path} = Join-Path $repoRoot" in scripts["build_windows.ps1"]
    assert '"--onedir"' in scripts["build_windows.ps1"]
    assert '"--windowed"' in scripts["build_windows.ps1"]
    assert '"--contents-directory=runtime"' in scripts["build_windows.ps1"]
    assert '"--name=SBBN-Toolbox"' in scripts["build_windows.ps1"]
    assert '"--version-file=$versionInfoPath"' in scripts["build_windows.ps1"]
    assert '"--add-data=$sourcePath;$($resource.destination)"' in scripts["build_windows.ps1"]
    assert (
        "Invoke-Checked $python ($pyinstallerArguments + $entrypointPath)"
        in scripts["build_windows.ps1"]
    )
    for dependency in ("fitz", "pymupdf", "pypdf", "img2pdf", "PIL"):
        assert f'"--hidden-import={dependency}"' in scripts["build_windows.ps1"]
    assert '"--onefile"' not in scripts["build_windows.ps1"]
    assert '"-3.12"' in scripts["build_windows.ps1"]
    assert "SBBN-Toolbox-Windows-x64.zip" in scripts["package_zip.ps1"]
    assert "Get-FileHash" in scripts["package_zip.ps1"]
    assert "SBBN-Toolbox.exe" in scripts["package_zip.ps1"]
    assert '"runtime"' in scripts["package_zip.ps1"]
    assert "SBBN-Toolbox-runtime.exe" not in scripts["smoke_test.ps1"]
    assert "--smoke-test" in scripts["smoke_test.ps1"]
    assert "Get-NetTCPConnection" in scripts["smoke_test.ps1"]


def test_pyinstaller_resources_resolve_from_repository_outside_working_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    manifest = json.loads(
        (REPOSITORY_ROOT / "packaging" / "pyinstaller_resources.json").read_text(encoding="utf-8")
    )

    resolved = [
        ((REPOSITORY_ROOT / item["source"]).resolve(), item["destination"])
        for item in manifest["data"]
    ]

    assert resolved == [
        (
            (REPOSITORY_ROOT / "src/sbbn_toolbox/ui/theme/stylesheet.qss").resolve(),
            "sbbn_toolbox/ui/theme",
        )
    ]
    assert all(source.is_file() for source, _ in resolved)


def test_zip_validation_normalizes_windows_entry_separators() -> None:
    package_script = (REPOSITORY_ROOT / "scripts" / "package_zip.ps1").read_text(encoding="utf-8")
    windows_entries = [
        r"SBBN-Toolbox\SBBN-Toolbox.exe",
        r"SBBN-Toolbox\config.json",
        r"SBBN-Toolbox\README.txt",
        r"SBBN-Toolbox\runtime\python312.dll",
    ]

    entries = [entry.replace("\\", "/") for entry in windows_entries]

    assert r"ForEach-Object { $_.FullName -replace '\\', '/' }" in package_script
    assert "SBBN-Toolbox/SBBN-Toolbox.exe" in entries
    assert "SBBN-Toolbox/config.json" in entries
    assert "SBBN-Toolbox/README.txt" in entries
    assert any(entry.startswith("SBBN-Toolbox/runtime/") for entry in entries)


def test_user_readme_contains_required_portable_guidance() -> None:
    readme = (REPOSITORY_ROOT / "packaging" / "README.txt").read_text(encoding="utf-8")
    lowered = readme.lower()

    for expected in (
        "décompressez entièrement",
        "directement depuis l’archive zip",
        "premier lancement",
        "paramètres",
        "localement",
        "jpg",
        "pdf",
        "smartscreen",
        "informations complémentaires",
    ):
        assert expected in lowered
    assert "signée numériquement" in lowered
    assert "n’est pas déclarée" in lowered


def test_application_source_imports_no_network_client() -> None:
    forbidden_roots = {
        "aiohttp",
        "ftplib",
        "http",
        "requests",
        "socket",
        "urllib",
        "webbrowser",
    }
    imported_roots: set[str] = set()
    for source in (REPOSITORY_ROOT / "src" / "sbbn_toolbox").rglob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".", 1)[0])

    assert imported_roots.isdisjoint(forbidden_roots)
