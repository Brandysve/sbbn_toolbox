import tomllib
from pathlib import Path

from sbbn_toolbox import __version__

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_application_version_comes_from_pyproject() -> None:
    payload = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert __version__ == payload["project"]["version"]
