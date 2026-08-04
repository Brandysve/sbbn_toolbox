import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_windows_version_info_is_generated_from_pyproject(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "example"\nversion = "2.3.4"\n', encoding="utf-8")
    output = tmp_path / "build" / "version.txt"

    result = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "packaging/generate_windows_version_info.py"),
            "--pyproject",
            str(pyproject),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    content = output.read_text(encoding="utf-8")
    assert "filevers=(2, 3, 4, 0)" in content
    assert 'StringStruct("ProductVersion", "2.3.4.0")' in content
    assert not list(output.parent.glob(".*.sbbn-partial-*"))
