"""Modèle de présentation de la fusion et des aperçus PDF."""

from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QRunnable, QThread, QThreadPool, Signal, Slot

from sbbn_toolbox.domain.pdf_page_item import PdfPageItem
from sbbn_toolbox.services.pdf_merge_service import (
    PdfMergeCancelled,
    PdfMergeService,
)
from sbbn_toolbox.services.preview_service import (
    PdfLoadCancelled,
    PdfLoadError,
    PreviewService,
)


class PdfLoadWorker(QObject):
    page_loaded = Signal(object)
    source_failed = Signal(str, str)
    progress = Signal(int)
    cancelled = Signal()
    finished = Signal()

    def __init__(
        self,
        service: PreviewService,
        paths: list[Path],
        cancellation: Event,
    ) -> None:
        super().__init__()
        self._service = service
        self._paths = paths
        self._cancellation = cancellation

    @Slot()
    def run(self) -> None:
        loaded = 0
        try:
            for path in self._paths:
                try:
                    for page in self._service.iter_document_pages(
                        path, is_cancelled=self._cancellation.is_set
                    ):
                        self.page_loaded.emit(page)
                        loaded += 1
                        self.progress.emit(loaded)
                except PdfLoadCancelled:
                    self.cancelled.emit()
                    return
                except PdfLoadError as error:
                    self.source_failed.emit(str(path.resolve()), str(error))
        finally:
            self.finished.emit()


class PreviewEmitter(QObject):
    ready = Signal(str, bytes)
    failed = Signal(str, str)


class PreviewTask(QRunnable):
    def __init__(
        self,
        service: PreviewService,
        page: PdfPageItem,
        emitter: PreviewEmitter,
    ) -> None:
        super().__init__()
        self._service = service
        self._page = page
        self._emitter = emitter

    @Slot()
    def run(self) -> None:
        try:
            payload = self._service.render_thumbnail(self._page)
            self._emitter.ready.emit(self._page.identifier, payload)
        except PdfLoadError as error:
            self._emitter.failed.emit(self._page.identifier, str(error))


class PdfMergeWorker(QObject):
    progress = Signal(int, int)
    succeeded = Signal(str)
    failed = Signal(str)
    cancelled = Signal()
    finished = Signal()

    def __init__(
        self,
        service: PdfMergeService,
        pages: list[PdfPageItem],
        destination: Path,
        overwrite: bool,
        cancellation: Event,
    ) -> None:
        super().__init__()
        self._service = service
        self._pages = pages
        self._destination = destination
        self._overwrite = overwrite
        self._cancellation = cancellation

    @Slot()
    def run(self) -> None:
        try:
            result = self._service.merge(
                self._pages,
                self._destination,
                overwrite=self._overwrite,
                progress=self.progress.emit,
                is_cancelled=self._cancellation.is_set,
            )
            self.succeeded.emit(str(result))
        except PdfMergeCancelled:
            self.cancelled.emit()
        except Exception as error:  # noqa: BLE001 - frontière thread/UI
            self.failed.emit(str(error))
        finally:
            self.finished.emit()


class PdfMergerViewModel(QObject):
    """Source de vérité de l'ordre global des pages PDF."""

    pages_changed = Signal(list)
    page_added = Signal(object)
    page_updated = Signal(object)
    load_failed = Signal(str)
    load_progress = Signal(int)
    thumbnail_ready = Signal(str, bytes)
    thumbnail_failed = Signal(str)
    merge_progress = Signal(int, int)
    busy_changed = Signal(bool)
    operation_cancelled = Signal()
    merge_succeeded = Signal(str)
    merge_failed = Signal(str)

    def __init__(
        self,
        preview_service: PreviewService | None = None,
        merge_service: PdfMergeService | None = None,
    ) -> None:
        super().__init__()
        self.preview_service = preview_service or PreviewService()
        self.merge_service = merge_service or PdfMergeService()
        self.pages: list[PdfPageItem] = []
        self.is_busy = False
        self._cancellation = Event()
        self._thread: QThread | None = None
        self._worker: QObject | None = None
        self._preview_pool = QThreadPool(self)
        self._preview_pool.setMaxThreadCount(2)
        self._preview_emitter = PreviewEmitter()
        self._preview_emitter.ready.connect(self.thumbnail_ready)
        self._preview_emitter.failed.connect(
            lambda _identifier, message: self.thumbnail_failed.emit(message)
        )

    def import_files(self, paths: list[Path]) -> None:
        if self.is_busy:
            return
        existing = {page.source_path for page in self.pages}
        unique: list[Path] = []
        for path in paths:
            resolved = path.resolve()
            if resolved in existing or resolved in unique:
                self.load_failed.emit(f"{path.name} : ce PDF est déjà ajouté.")
            else:
                unique.append(resolved)
        if not unique:
            return
        self._cancellation.clear()
        self._set_busy(True)
        thread = QThread(self)
        worker = PdfLoadWorker(self.preview_service, unique, self._cancellation)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.page_loaded.connect(self._page_loaded)
        worker.source_failed.connect(self._source_failed)
        worker.progress.connect(self.load_progress)
        worker.cancelled.connect(self.operation_cancelled)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._operation_finished)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        thread.start()

    @Slot(object)
    def _page_loaded(self, page: PdfPageItem) -> None:
        self.pages.append(page)
        self.page_added.emit(page)

    @Slot(str, str)
    def _source_failed(self, path: str, message: str) -> None:
        source = Path(path)
        self.pages = [page for page in self.pages if page.source_path != source]
        self.preview_service.clear_source(source)
        self.pages_changed.emit(list(self.pages))
        self.load_failed.emit(f"{source.name} : {message}")

    def request_thumbnail(self, identifier: str, priority: int = 0) -> None:
        page = self._find(identifier)
        if page is None:
            return
        self._preview_pool.start(
            PreviewTask(self.preview_service, page, self._preview_emitter),
            priority,
        )

    def reorder(self, identifiers: list[str]) -> None:
        by_id = {page.identifier: page for page in self.pages}
        if set(identifiers) != set(by_id):
            return
        self.pages = [by_id[identifier] for identifier in identifiers]
        self.pages_changed.emit(list(self.pages))

    def rotate_selected(self, identifiers: list[str], degrees: int = 90) -> None:
        selected = set(identifiers)
        updated: list[PdfPageItem] = []
        for page in self.pages:
            if page.identifier in selected:
                self.preview_service.clear_page(page)
                page = page.rotated(degrees)
                self.page_updated.emit(page)
            updated.append(page)
        self.pages = updated
        self.pages_changed.emit(list(self.pages))

    def remove_selected(self, identifiers: list[str]) -> None:
        selected = set(identifiers)
        removed_pages = [page for page in self.pages if page.identifier in selected]
        removed_sources = {page.source_path for page in removed_pages}
        for page in removed_pages:
            self.preview_service.clear_page(page)
        self.pages = [page for page in self.pages if page.identifier not in selected]
        remaining_sources = {page.source_path for page in self.pages}
        for source in removed_sources - remaining_sources:
            self.preview_service.clear_source(source)
        self.pages_changed.emit(list(self.pages))

    def clear(self) -> None:
        if not self.is_busy:
            self.pages.clear()
            self.preview_service.clear()
            self.pages_changed.emit([])

    def start_merge(self, destination: Path, *, overwrite: bool) -> None:
        if self.is_busy or not self.pages:
            return
        self._cancellation.clear()
        self._set_busy(True)
        thread = QThread(self)
        worker = PdfMergeWorker(
            self.merge_service,
            list(self.pages),
            destination,
            overwrite,
            self._cancellation,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.merge_progress)
        worker.succeeded.connect(self.merge_succeeded)
        worker.failed.connect(self.merge_failed)
        worker.cancelled.connect(self.operation_cancelled)
        worker.finished.connect(self.preview_service.clear)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._operation_finished)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        thread.start()

    def cancel(self) -> None:
        self._cancellation.set()

    def shutdown(self) -> None:
        self.cancel()
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()
        self._preview_pool.waitForDone()
        self.preview_service.clear()

    def _find(self, identifier: str) -> PdfPageItem | None:
        return next((page for page in self.pages if page.identifier == identifier), None)

    @Slot()
    def _operation_finished(self) -> None:
        self._thread = None
        self._worker = None
        self.pages_changed.emit(list(self.pages))
        self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self.is_busy = busy
        self.busy_changed.emit(busy)
