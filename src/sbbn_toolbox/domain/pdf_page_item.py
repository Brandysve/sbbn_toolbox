"""Modèle indépendant représentant une page PDF source."""

from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class PdfPageItem:
    """Référence légère vers une page, sans recopier son contenu."""

    source_path: Path
    source_page_index: int
    display_page_number: int
    source_display_name: str
    width: float
    height: float
    rotation: int = 0
    identifier: str = ""

    def __post_init__(self) -> None:
        if self.source_page_index < 0 or self.display_page_number < 1:
            raise ValueError("Le numéro de page est invalide.")
        if self.rotation not in {0, 90, 180, 270}:
            raise ValueError("La rotation doit être un multiple de 90 degrés.")
        if not self.identifier:
            object.__setattr__(self, "identifier", uuid4().hex)

    def rotated(self, degrees: int = 90) -> "PdfPageItem":
        return replace(self, rotation=(self.rotation + degrees) % 360)
