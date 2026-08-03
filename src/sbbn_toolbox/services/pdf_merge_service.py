"""Fusion atomique de pages PDF référencées par le modèle."""

import os
import stat
from collections.abc import Callable, Sequence
from pathlib import Path
from uuid import uuid4

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from sbbn_toolbox.domain.pdf_page_item import PdfPageItem

ProgressCallback = Callable[[int, int], None]
CancelCallback = Callable[[], bool]


class PdfMergeError(RuntimeError):
    """Erreur de fusion présentable à l'utilisateur."""


class PdfMergeCancelled(PdfMergeError):
    """Fusion annulée entre deux pages."""


class PdfDestinationExistsError(PdfMergeError):
    """Écrasement non autorisé."""


class PdfMergeService:
    """Assembler les pages dans l'ordre exact du tableau fourni."""

    def merge(
        self,
        pages: Sequence[PdfPageItem],
        destination: Path,
        *,
        overwrite: bool = False,
        progress: ProgressCallback | None = None,
        is_cancelled: CancelCallback | None = None,
    ) -> Path:
        if not pages:
            raise PdfMergeError("Aucune page à fusionner.")
        target = destination.resolve()
        if target.suffix.lower() != ".pdf":
            target = target.with_suffix(".pdf")
        if target.exists() and not overwrite:
            raise PdfDestinationExistsError("Le fichier de destination existe déjà.")
        self._ensure_destination_writable(target)
        partial = target.parent / f".{target.name}.sbbn-partial-{uuid4().hex}.pdf"
        readers: dict[Path, PdfReader] = {}
        writer = PdfWriter()
        try:
            for index, item in enumerate(pages, start=1):
                if is_cancelled is not None and is_cancelled():
                    raise PdfMergeCancelled("La fusion a été annulée.")
                if not item.source_path.is_file():
                    raise PdfMergeError(f"Le PDF « {item.source_display_name} » est inaccessible.")
                reader = readers.get(item.source_path)
                if reader is None:
                    reader = PdfReader(item.source_path)
                    if reader.is_encrypted:
                        raise PdfMergeError("Les PDF protégés ne sont pas pris en charge.")
                    readers[item.source_path] = reader
                if item.source_page_index >= len(reader.pages):
                    raise PdfMergeError("Une page source n’existe plus.")
                added_page = writer.add_page(reader.pages[item.source_page_index])
                if item.rotation:
                    added_page.rotate(item.rotation)
                if progress is not None:
                    progress(index, len(pages))
            if is_cancelled is not None and is_cancelled():
                raise PdfMergeCancelled("La fusion a été annulée.")
            with partial.open("wb") as stream:
                writer.write(stream)
                stream.flush()
                os.fsync(stream.fileno())
            if target.exists() and not overwrite:
                raise PdfDestinationExistsError("Le fichier de destination existe déjà.")
            os.replace(partial, target)
            return target
        except PdfMergeError:
            raise
        except (OSError, PdfReadError, ValueError) as error:
            raise PdfMergeError(
                "La fusion a échoué. Vérifiez les sources et l’espace disque disponible."
            ) from error
        finally:
            readers.clear()
            partial.unlink(missing_ok=True)

    @staticmethod
    def _ensure_destination_writable(destination: Path) -> None:
        if not destination.parent.is_dir():
            raise PdfMergeError("Le dossier de destination n’existe pas.")
        mode = destination.parent.stat().st_mode
        if not mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
            raise PdfMergeError("Le dossier de destination est en lecture seule.")
