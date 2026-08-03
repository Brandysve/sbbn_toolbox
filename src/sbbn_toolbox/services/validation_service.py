"""Validation réelle des images importées."""

from pathlib import Path

from PIL import Image, UnidentifiedImageError

from sbbn_toolbox.domain.image_item import ImageItem

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}
FORMAT_EXTENSIONS = {
    "JPEG": {".jpg", ".jpeg"},
    "PNG": {".png"},
    "BMP": {".bmp"},
}


class ImageValidationError(ValueError):
    """L'image ne peut pas être importée en sécurité."""


class ImageValidationService:
    """Valider extension, signature, décodage et dimensions."""

    def validate(self, path: Path) -> ImageItem:
        """Créer un modèle seulement après décodage complet de l'image."""
        resolved = path.resolve()
        extension = resolved.suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            raise ImageValidationError("Extension non prise en charge.")
        if not resolved.is_file():
            raise ImageValidationError("Le fichier est inaccessible ou a été supprimé.")
        try:
            with Image.open(resolved) as image:
                detected_format = image.format
                image.verify()
            with Image.open(resolved) as image:
                image.load()
                width, height = image.size
        except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
            raise ImageValidationError("Le contenu de l’image est invalide ou corrompu.") from error
        if detected_format not in FORMAT_EXTENSIONS:
            raise ImageValidationError("Le format réel de l’image n’est pas pris en charge.")
        if extension not in FORMAT_EXTENSIONS[detected_format]:
            raise ImageValidationError("L’extension ne correspond pas au contenu réel de l’image.")
        return ImageItem(
            source_path=resolved,
            display_name=resolved.name,
            width=width,
            height=height,
            format=detected_format,
        )
