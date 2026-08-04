import sys
from pathlib import Path

import pytest

from sbbn_toolbox.infrastructure import paths


def test_program_directory_uses_source_root_in_development(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delattr(sys, "frozen", raising=False)

    assert paths.program_directory() == Path(paths.__file__).resolve().parents[3]


def test_program_directory_uses_executable_when_compiled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "SBBN Toolbox.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))

    assert paths.program_directory() == tmp_path.resolve()
