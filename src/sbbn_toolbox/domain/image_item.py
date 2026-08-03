"""Modèle indépendant représentant une image importée."""

from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class ImageItem:
    """Image source et transformations demandées, sans modifier le fichier."""

    source_path: Path
    display_name: str
    width: int
    height: int
    format: str
    rotation: int = 0
    identifier: str = ""

    def __post_init__(self) -> None:
        if self.rotation not in {0, 90, 180, 270}:
            raise ValueError("La rotation doit être un multiple de 90 degrés.")
        if not self.identifier:
            object.__setattr__(self, "identifier", uuid4().hex)

    def rotated(self, degrees: int = 90) -> "ImageItem":
        """Retourner une nouvelle valeur avec une rotation normalisée."""
        return replace(self, rotation=(self.rotation + degrees) % 360)
