"""Résolution de la version issue exclusivement de ``pyproject.toml``."""

import tomllib
from importlib.metadata import version
from pathlib import Path


def application_version() -> str:
    """Lire la source en développement, ou ses métadonnées dans le paquet distribué."""
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if pyproject_path.is_file():
        payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        project = payload.get("project")
        project_version: object = project.get("version") if isinstance(project, dict) else None
        if isinstance(project_version, str):
            return project_version
        raise RuntimeError("La version du projet est introuvable.")
    return version("sbbn-toolbox")
