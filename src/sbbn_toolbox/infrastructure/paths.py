"""Résolution des chemins de l'application portable."""

import sys
from pathlib import Path


def program_directory() -> Path:
    """Retourner le dossier qui contient la configuration portable.

    En développement, le point de départ est la racine du dépôt source,
    indépendamment du dossier courant. Dans l'application compilée, il s'agit du
    dossier qui contient l'exécutable.
    """
    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        executable_directory = Path(sys.executable).resolve().parent
        if (
            executable_directory.name.lower() == "runtime"
            and (executable_directory.parent / "SBBN-Toolbox.exe").is_file()
        ):
            return executable_directory.parent
        return executable_directory
    return Path(__file__).resolve().parents[3]
