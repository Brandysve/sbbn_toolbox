"""Conversion sûre et atomique d'images en PDF multipage."""

import io
import os
import stat
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast
from uuid import uuid4

import img2pdf
from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter

from sbbn_toolbox.domain.image_item import ImageItem

ProgressCallback = Callable[[int, int], None]
CancelCallback = Callable[[], bool]


class PageMode(StrEnum):
    ORIGINAL = "original"
    A4 = "a4"


class PageOrientation(StrEnum):
    AUTO = "automatic"
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"


@dataclass(frozen=True, slots=True)
class ImagePdfOptions:
    """Options de mise en page sans étirement ni rognage."""

    page_mode: PageMode = PageMode.ORIGINAL
    orientation: PageOrientation = PageOrientation.AUTO
    margin_mm: float = 0.0

    def __post_init__(self) -> None:
        if not 0 <= self.margin_mm <= 50:
            raise ValueError("Les marges doivent être comprises entre 0 et 50 mm.")


class ImageConversionError(RuntimeError):
    """Erreur de conversion présentable à l'utilisateur."""


class ImageConversionCancelled(ImageConversionError):
    """Conversion annulée entre deux images."""


class DestinationExistsError(ImageConversionError):
    """La destination existe et l'écrasement n'est pas autorisé."""


class ImageToPdfService:
    """Produire un PDF dans l'ordre des modèles fournis."""

    def convert(
        self,
        items: Sequence[ImageItem],
        destination: Path,
        options: ImagePdfOptions,
        *,
        overwrite: bool = False,
        progress: ProgressCallback | None = None,
        is_cancelled: CancelCallback | None = None,
    ) -> Path:
        if not items:
            raise ImageConversionError("Aucune image à convertir.")
        target = destination.resolve()
        if target.suffix.lower() != ".pdf":
            target = target.with_suffix(".pdf")
        if target.exists() and not overwrite:
            raise DestinationExistsError("Le fichier de destination existe déjà.")
        self._ensure_destination_writable(target)
        partial = target.parent / f".{target.name}.sbbn-partial-{uuid4().hex}.pdf"
        writer = PdfWriter()
        try:
            for index, item in enumerate(items, start=1):
                if is_cancelled is not None and is_cancelled():
                    raise ImageConversionCancelled("La conversion a été annulée.")
                page_pdf = self._image_page_pdf(item, options)
                reader = PdfReader(io.BytesIO(page_pdf))
                writer.add_page(reader.pages[0])
                if progress is not None:
                    progress(index, len(items))
            if is_cancelled is not None and is_cancelled():
                raise ImageConversionCancelled("La conversion a été annulée.")
            with partial.open("wb") as stream:
                writer.write(stream)
                stream.flush()
                os.fsync(stream.fileno())
            if target.exists() and not overwrite:
                raise DestinationExistsError("Le fichier de destination existe déjà.")
            os.replace(partial, target)
            return target
        except ImageConversionError:
            raise
        except Exception as error:  # noqa: BLE001 - frontière du service métier
            raise ImageConversionError(
                "La conversion a échoué. Vérifiez les images et l’espace disque disponible."
            ) from error
        finally:
            partial.unlink(missing_ok=True)

    def _image_page_pdf(self, item: ImageItem, options: ImagePdfOptions) -> bytes:
        if not item.source_path.is_file():
            raise ImageConversionError(f"L’image « {item.display_name} » est inaccessible.")
        layout = self._layout_function(options)
        if item.format == "JPEG" and item.rotation == 0:
            try:
                return cast(bytes, img2pdf.convert(str(item.source_path), layout_fun=layout))
            except (
                img2pdf.ExifOrientationError,
                img2pdf.JpegColorspaceError,
                img2pdf.UnsupportedColorspaceError,
            ):
                pass
        normalized = self._normalized_image(item)
        return cast(bytes, img2pdf.convert(normalized, layout_fun=layout))

    @staticmethod
    def _normalized_image(item: ImageItem) -> bytes:
        try:
            with Image.open(item.source_path) as source:
                source.load()
                image = ImageOps.exif_transpose(source).copy()
            if item.rotation:
                image = image.rotate(-item.rotation, expand=True)
            output = io.BytesIO()
            if "A" in image.getbands() or item.format == "PNG":
                image.save(output, format="PNG")
            else:
                image.convert("RGB").save(output, format="JPEG", quality=95)
            return output.getvalue()
        except OSError as error:
            raise ImageConversionError(
                f"L’image « {item.display_name} » est invalide ou inaccessible."
            ) from error

    @staticmethod
    def _layout_function(
        options: ImagePdfOptions,
    ) -> Callable[..., tuple[float, float, float, float]]:
        margin = img2pdf.mm_to_pt(options.margin_mm)
        if options.page_mode is PageMode.A4:
            portrait = (img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297))
            if options.orientation is PageOrientation.LANDSCAPE:
                page_size = (portrait[1], portrait[0])
                auto_orient = False
            elif options.orientation is PageOrientation.PORTRAIT:
                page_size = portrait
                auto_orient = False
            else:
                page_size = portrait
                auto_orient = True
            return cast(
                Callable[..., tuple[float, float, float, float]],
                img2pdf.get_layout_fun(
                    pagesize=page_size,
                    border=(margin, margin),
                    fit=img2pdf.FitMode.into,
                    auto_orient=auto_orient,
                ),
            )

        def original_layout(
            image_width: int,
            image_height: int,
            dpi: tuple[float, float],
        ) -> tuple[float, float, float, float]:
            dpi_x = dpi[0] or 96
            dpi_y = dpi[1] or 96
            width = image_width * 72 / dpi_x
            height = image_height * 72 / dpi_y
            return width + 2 * margin, height + 2 * margin, width, height

        return original_layout

    @staticmethod
    def _ensure_destination_writable(destination: Path) -> None:
        if not destination.parent.is_dir():
            raise ImageConversionError("Le dossier de destination n’existe pas.")
        mode = destination.parent.stat().st_mode
        if not mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
            raise ImageConversionError("Le dossier de destination est en lecture seule.")
