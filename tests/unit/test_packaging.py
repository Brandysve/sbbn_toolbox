import ast
import json
from pathlib import Path

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
    assert '"--onedir"' in scripts["build_windows.ps1"]
    assert '"--windowed"' in scripts["build_windows.ps1"]
    assert '"--contents-directory=runtime"' in scripts["build_windows.ps1"]
    assert '"--name=SBBN-Toolbox"' in scripts["build_windows.ps1"]
    assert '"--version-file=packaging\\windows_version_info.txt"' in scripts["build_windows.ps1"]
    assert "stylesheet.qss;sbbn_toolbox\\ui\\theme" in scripts["build_windows.ps1"]
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
