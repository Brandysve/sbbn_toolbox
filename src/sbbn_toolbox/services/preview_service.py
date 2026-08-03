"""Lecture PyMuPDF et cache mémoire borné des vignettes PDF."""

from collections import OrderedDict
from collections.abc import Callable, Iterator
from pathlib import Path
from threading import RLock
from typing import cast

import fitz

from sbbn_toolbox.domain.pdf_page_item import PdfPageItem

CancelCallback = Callable[[], bool]
CacheKey = tuple[Path, int, int, int]


class PdfLoadError(RuntimeError):
    """Document PDF inutilisable dans le MVP."""


class PdfLoadCancelled(PdfLoadError):
    """Chargement annulé entre deux pages."""


class PreviewService:
    """Charger les métadonnées et rendre les aperçus à la demande."""

    def __init__(self, max_cache_bytes: int = 16 * 1024 * 1024) -> None:
        if max_cache_bytes <= 0:
            raise ValueError("La taille du cache doit être positive.")
        self.max_cache_bytes = max_cache_bytes
        self._cache: OrderedDict[CacheKey, bytes] = OrderedDict()
        self._cache_size = 0
        self._lock = RLock()

    @property
    def cache_size_bytes(self) -> int:
        with self._lock:
            return self._cache_size

    @property
    def cache_entry_count(self) -> int:
        with self._lock:
            return len(self._cache)

    def iter_document_pages(
        self,
        path: Path,
        *,
        is_cancelled: CancelCallback | None = None,
    ) -> Iterator[PdfPageItem]:
        """Valider réellement puis émettre les pages une à une."""
        resolved = path.resolve()
        if resolved.suffix.lower() != ".pdf":
            raise PdfLoadError("Extension PDF invalide.")
        if not resolved.is_file():
            raise PdfLoadError("Le fichier PDF est inaccessible ou a été supprimé.")
        try:
            with fitz.open(resolved) as document:
                if document.needs_pass:
                    raise PdfLoadError(
                        "Les PDF protégés par mot de passe ne sont pas pris en charge."
                    )
                if document.page_count == 0:
                    raise PdfLoadError("Le PDF est vide.")
                for index in range(document.page_count):
                    if is_cancelled is not None and is_cancelled():
                        raise PdfLoadCancelled("Le chargement a été annulé.")
                    page = document.load_page(index)
                    rect = page.rect
                    yield PdfPageItem(
                        source_path=resolved,
                        source_page_index=index,
                        display_page_number=index + 1,
                        source_display_name=resolved.name,
                        width=rect.width,
                        height=rect.height,
                    )
        except PdfLoadError:
            raise
        except (fitz.FileDataError, RuntimeError, ValueError, OSError) as error:
            raise PdfLoadError("Le PDF est vide, corrompu ou inaccessible.") from error

    def render_thumbnail(self, item: PdfPageItem, width: int = 180) -> bytes:
        """Rendre une vignette PNG en mémoire, avec cache LRU borné."""
        key = (item.source_path, item.source_page_index, item.rotation, width)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                return cached
        if not item.source_path.is_file():
            raise PdfLoadError("Le fichier PDF source a été supprimé.")
        try:
            with fitz.open(item.source_path) as document:
                if document.needs_pass:
                    raise PdfLoadError(
                        "Les PDF protégés par mot de passe ne sont pas pris en charge."
                    )
                page = document.load_page(item.source_page_index)
                scale = width / max(page.rect.width, 1)
                matrix = fitz.Matrix(scale, scale).prerotate(item.rotation)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                payload = cast(bytes, pixmap.tobytes("png"))
        except PdfLoadError:
            raise
        except (fitz.FileDataError, RuntimeError, ValueError, OSError) as error:
            raise PdfLoadError("Impossible de générer l’aperçu de la page.") from error
        self._store(key, payload)
        return payload

    def clear_source(self, source_path: Path) -> None:
        with self._lock:
            keys = [key for key in self._cache if key[0] == source_path]
            for key in keys:
                self._cache_size -= len(self._cache.pop(key))

    def clear_page(self, page: PdfPageItem) -> None:
        """Libérer toutes les variantes d'aperçu d'une page."""
        with self._lock:
            keys = [
                key
                for key in self._cache
                if key[0] == page.source_path and key[1] == page.source_page_index
            ]
            for key in keys:
                self._cache_size -= len(self._cache.pop(key))

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._cache_size = 0

    def _store(self, key: CacheKey, payload: bytes) -> None:
        with self._lock:
            previous = self._cache.pop(key, None)
            if previous is not None:
                self._cache_size -= len(previous)
            if len(payload) > self.max_cache_bytes:
                return
            self._cache[key] = payload
            self._cache_size += len(payload)
            while self._cache_size > self.max_cache_bytes:
                _, removed = self._cache.popitem(last=False)
                self._cache_size -= len(removed)
