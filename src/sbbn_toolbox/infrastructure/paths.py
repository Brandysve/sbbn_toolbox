"""Résolution des chemins de l'application portable."""

import sys
from pathlib import Path


def program_directory() -> Path:
    """Retourner le dossier qui contient la configuration portable.

    En développement, le point de départ est la racine du dépôt source,
    indépendamment du dossier courant. Dans l'application compilée, il s'agit du
    dossier qui contient l'exécutable.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]
