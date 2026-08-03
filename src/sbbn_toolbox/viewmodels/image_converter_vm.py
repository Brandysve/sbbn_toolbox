"""Modèle de présentation du parcours Images vers PDF."""

from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QThread, Signal, Slot

from sbbn_toolbox.domain.image_item import ImageItem
from sbbn_toolbox.services.image_to_pdf_service import (
    ImageConversionCancelled,
    ImagePdfOptions,
    ImageToPdfService,
)
from sbbn_toolbox.services.validation_service import (
    ImageValidationError,
    ImageValidationService,
)


class ConversionWorker(QObject):
    """Exécuter une conversion dans un thread dédié."""

    progress = Signal(int, int)
    succeeded = Signal(str)
    failed = Signal(str)
    cancelled = Signal()
    finished = Signal()

    def __init__(
        self,
        service: ImageToPdfService,
        items: list[ImageItem],
        destination: Path,
        options: ImagePdfOptions,
        overwrite: bool,
        cancellation: Event,
    ) -> None:
        super().__init__()
        self._service = service
        self._items = items
        self._destination = destination
        self._options = options
        self._overwrite = overwrite
        self._cancellation = cancellation

    @Slot()
    def run(self) -> None:
        """Convertir puis toujours annoncer la fin du travail."""
        try:
            result = self._service.convert(
                self._items,
                self._destination,
                self._options,
                overwrite=self._overwrite,
                progress=self.progress.emit,
                is_cancelled=self._cancellation.is_set,
            )
            self.succeeded.emit(str(result))
        except ImageConversionCancelled:
            self.cancelled.emit()
        except Exception as error:  # noqa: BLE001 - frontière thread/UI
            self.failed.emit(str(error))
        finally:
            self.finished.emit()


class ImageConverterViewModel(QObject):
    """Maintenir l'ordre et coordonner la conversion sans dépendre des widgets."""

    items_changed = Signal(list)
    import_failed = Signal(str)
    progress_changed = Signal(int, int)
    busy_changed = Signal(bool)
    conversion_succeeded = Signal(str)
    conversion_failed = Signal(str)
    conversion_cancelled = Signal()

    def __init__(
        self,
        service: ImageToPdfService | None = None,
        validator: ImageValidationService | None = None,
    ) -> None:
        super().__init__()
        self._service = service or ImageToPdfService()
        self._validator = validator or ImageValidationService()
        self.items: list[ImageItem] = []
        self.is_busy = False
        self._thread: QThread | None = None
        self._worker: ConversionWorker | None = None
        self._cancellation = Event()

    def import_files(self, paths: list[Path]) -> None:
        """Valider et ajouter les images acceptées sans modifier leurs sources."""
        if self.is_busy:
            return
        existing = {item.source_path for item in self.items}
        for path in paths:
            try:
                item = self._validator.validate(path)
            except ImageValidationError as error:
                self.import_failed.emit(f"{path.name} : {error}")
                continue
            if item.source_path not in existing:
                self.items.append(item)
                existing.add(item.source_path)
        self.items_changed.emit(list(self.items))

    def reorder(self, identifiers: list[str]) -> None:
        """Appliquer exactement l'ordre issu du glisser-déposer."""
        by_id = {item.identifier: item for item in self.items}
        if set(identifiers) != set(by_id):
            return
        self.items = [by_id[identifier] for identifier in identifiers]
        self.items_changed.emit(list(self.items))

    def rotate(self, identifier: str, degrees: int = 90) -> None:
        self.items = [
            item.rotated(degrees) if item.identifier == identifier else item for item in self.items
        ]
        self.items_changed.emit(list(self.items))

    def remove(self, identifier: str) -> None:
        self.items = [item for item in self.items if item.identifier != identifier]
        self.items_changed.emit(list(self.items))

    def clear(self) -> None:
        if not self.is_busy:
            self.items.clear()
            self.items_changed.emit([])

    def start_conversion(
        self,
        destination: Path,
        options: ImagePdfOptions,
        *,
        overwrite: bool,
    ) -> None:
        """Démarrer la conversion hors du thread UI."""
        if self.is_busy or not self.items:
            return
        self._cancellation.clear()
        self._set_busy(True)
        thread = QThread(self)
        worker = ConversionWorker(
            self._service,
            list(self.items),
            destination,
            options,
            overwrite,
            self._cancellation,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.progress_changed)
        worker.succeeded.connect(self.conversion_succeeded)
        worker.failed.connect(self.conversion_failed)
        worker.cancelled.connect(self.conversion_cancelled)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._conversion_finished)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        thread.start()

    def cancel(self) -> None:
        """Demander une annulation vérifiée entre deux images."""
        self._cancellation.set()

    def shutdown(self) -> None:
        """Annuler et attendre le nettoyage avant la fermeture de l'application."""
        self.cancel()
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()

    @Slot()
    def _conversion_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self.is_busy = busy
        self.busy_changed.emit(busy)
