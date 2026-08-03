"""Parcours complet de fusion et réorganisation de pages PDF."""

from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from sbbn_toolbox.constants import (
    ADD_MORE_PDF,
    ADD_PDF,
    CANCEL_PDF_OPERATION,
    CLEAR_PDF_PAGES,
    CLOSE,
    MERGE_PDF,
    OPEN_FOLDER,
    PDF_DESCRIPTION,
    PDF_DROP_DESCRIPTION,
    PDF_DROP_TITLE,
    PDF_EMPTY_DESCRIPTION,
    PDF_EMPTY_TITLE,
    PDF_FILES_INPUT_FILTER,
    PDF_IMPORT_ERROR_TITLE,
    PDF_LOADING_PROGRESS,
    PDF_MERGE_PROGRESS,
    PDF_OPERATION_CANCELLED,
    PDF_OVERWRITE_MESSAGE,
    PDF_OVERWRITE_TITLE,
    PDF_SAVE_TITLE,
    PDF_SUCCESS_MESSAGE,
    PDF_SUCCESS_TITLE,
    PDF_TITLE,
    REMOVE_SELECTED_PAGES,
    REORDER_PDF_DOCUMENTS,
    ROTATE_SELECTED_PAGES,
)
from sbbn_toolbox.domain.pdf_page_item import PdfPageItem
from sbbn_toolbox.ui.theme.tokens import SPACING
from sbbn_toolbox.ui.widgets.buttons import ActionButton
from sbbn_toolbox.ui.widgets.drop_zone import DropZone
from sbbn_toolbox.ui.widgets.empty_state import EmptyState
from sbbn_toolbox.ui.widgets.page_header import PageHeader
from sbbn_toolbox.ui.widgets.pdf_page_grid import PdfPageGrid
from sbbn_toolbox.viewmodels.pdf_merger_vm import PdfMergerViewModel


class PdfMergerPage(QWidget):
    """Charger, ordonner et fusionner des références de pages PDF."""

    notification_requested = Signal(str)

    def __init__(
        self,
        viewmodel: PdfMergerViewModel | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.viewmodel = viewmodel or PdfMergerViewModel()
        self._selected: list[str] = []
        self._operation_kind = "load"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.xxxl, SPACING.xxl, SPACING.xxxl, SPACING.xxl)
        layout.setSpacing(SPACING.xl)

        layout.addWidget(PageHeader(PDF_TITLE, PDF_DESCRIPTION))

        self.drop_zone = DropZone(PDF_DROP_TITLE, PDF_DROP_DESCRIPTION, ADD_PDF)
        self.drop_zone.selection_requested.connect(self._choose_pdfs)
        self.drop_zone.files_dropped.connect(self._import_dropped_files)
        layout.addWidget(self.drop_zone)
        self.empty_state = EmptyState(PDF_EMPTY_TITLE, PDF_EMPTY_DESCRIPTION)
        layout.addWidget(self.empty_state, stretch=1)
        self.grid = PdfPageGrid()
        self.grid.setMinimumHeight(300)
        self.grid.hide()
        self.grid.order_changed.connect(self.viewmodel.reorder)
        self.grid.selection_changed.connect(self._selection_changed)
        self.grid.preview_requested.connect(self.viewmodel.request_thumbnail)
        self.document_mode_checkbox = QCheckBox(REORDER_PDF_DOCUMENTS)
        self.document_mode_checkbox.setObjectName("documentModeCheckbox")
        self.document_mode_checkbox.toggled.connect(self._set_document_mode)
        self.document_mode_checkbox.hide()
        layout.addWidget(self.document_mode_checkbox)
        layout.addWidget(self.grid, stretch=1)

        actions = QVBoxLayout()
        document_actions = QHBoxLayout()
        selection_actions = QHBoxLayout()
        self.add_more_button = ActionButton(ADD_MORE_PDF, variant="secondary")
        self.add_more_button.setObjectName("addMorePdfButton")
        self.add_more_button.clicked.connect(self._choose_pdfs)
        self.add_more_button.hide()
        document_actions.addWidget(self.add_more_button)
        self.clear_button = ActionButton(CLEAR_PDF_PAGES, variant="secondary")
        self.clear_button.setEnabled(False)
        self.clear_button.clicked.connect(self.viewmodel.clear)
        document_actions.addWidget(self.clear_button)
        document_actions.addStretch()
        actions.addLayout(document_actions)
        self.rotate_button = ActionButton(ROTATE_SELECTED_PAGES, variant="secondary")
        self.rotate_button.setEnabled(False)
        self.rotate_button.clicked.connect(lambda: self.viewmodel.rotate_selected(self._selected))
        selection_actions.addWidget(self.rotate_button)
        self.remove_button = ActionButton(REMOVE_SELECTED_PAGES, variant="secondary")
        self.remove_button.setEnabled(False)
        self.remove_button.clicked.connect(lambda: self.viewmodel.remove_selected(self._selected))
        selection_actions.addWidget(self.remove_button)
        selection_actions.addStretch()
        actions.addLayout(selection_actions)
        output_actions = QHBoxLayout()
        output_actions.addStretch()
        self.cancel_button = ActionButton(CANCEL_PDF_OPERATION, variant="secondary")
        self.cancel_button.setObjectName("cancelPdfOperationButton")
        self.cancel_button.clicked.connect(self.viewmodel.cancel)
        self.cancel_button.hide()
        output_actions.addWidget(self.cancel_button)
        self.merge_button = ActionButton(MERGE_PDF)
        self.merge_button.setEnabled(False)
        self.merge_button.setToolTip(PDF_EMPTY_TITLE)
        self.merge_button.clicked.connect(self._choose_destination)
        output_actions.addWidget(self.merge_button)
        actions.addLayout(output_actions)
        layout.addLayout(actions)

        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)

        self.viewmodel.page_added.connect(self._page_added)
        self.viewmodel.pages_changed.connect(self._sync_pages)
        self.viewmodel.load_failed.connect(self._show_error)
        self.viewmodel.thumbnail_ready.connect(self.grid.set_thumbnail)
        self.viewmodel.thumbnail_failed.connect(self.notification_requested)
        self.viewmodel.load_progress.connect(self._load_progress)
        self.viewmodel.merge_progress.connect(self._merge_progress)
        self.viewmodel.busy_changed.connect(self._set_busy)
        self.viewmodel.operation_cancelled.connect(
            lambda: self.notification_requested.emit(PDF_OPERATION_CANCELLED)
        )
        self.viewmodel.merge_succeeded.connect(self._merge_succeeded)
        self.viewmodel.merge_failed.connect(self._show_error)

    def _choose_pdfs(self) -> None:
        filenames, _ = QFileDialog.getOpenFileNames(self, ADD_PDF, "", PDF_FILES_INPUT_FILTER)
        self._start_import([Path(filename) for filename in filenames])

    def _import_dropped_files(self, filenames: list[str]) -> None:
        self._start_import([Path(filename) for filename in filenames])

    def _start_import(self, paths: list[Path]) -> None:
        if paths:
            self._operation_kind = "load"
            self.viewmodel.import_files(paths)

    def _choose_destination(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(self, PDF_SAVE_TITLE, "", PDF_FILES_INPUT_FILTER)
        if not filename:
            return
        destination = Path(filename)
        if destination.suffix.lower() != ".pdf":
            destination = destination.with_suffix(".pdf")
        overwrite = False
        if destination.exists():
            answer = QMessageBox.question(
                self,
                PDF_OVERWRITE_TITLE,
                PDF_OVERWRITE_MESSAGE,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer is not QMessageBox.StandardButton.Yes:
                return
            overwrite = True
        self._operation_kind = "merge"
        self.viewmodel.start_merge(destination, overwrite=overwrite)

    def _page_added(self, page: PdfPageItem) -> None:
        self.grid.append_page(page)
        self.grid.show()
        self.drop_zone.hide()
        self.add_more_button.show()
        self.document_mode_checkbox.show()
        self.empty_state.hide()

    def _sync_pages(self, pages: list[PdfPageItem]) -> None:
        self.grid.set_pages(pages)
        self.grid.setVisible(bool(pages))
        self.drop_zone.setVisible(not pages)
        self.add_more_button.setVisible(bool(pages))
        self.document_mode_checkbox.setVisible(bool(pages))
        self.empty_state.setVisible(not pages)
        self.clear_button.setEnabled(bool(pages) and not self.viewmodel.is_busy)
        self.merge_button.setEnabled(bool(pages) and not self.viewmodel.is_busy)
        self._selection_changed([])

    def _selection_changed(self, identifiers: list[str]) -> None:
        self._selected = identifiers
        enabled = bool(identifiers) and not self.viewmodel.is_busy
        self.rotate_button.setEnabled(enabled)
        self.remove_button.setEnabled(enabled)

    def _set_busy(self, busy: bool) -> None:
        self.drop_zone.setEnabled(not busy)
        self.add_more_button.setEnabled(not busy)
        self.document_mode_checkbox.setEnabled(not busy)
        self.grid.setEnabled(not busy)
        self.clear_button.setEnabled(not busy and bool(self.viewmodel.pages))
        self.merge_button.setEnabled(not busy and bool(self.viewmodel.pages))
        self.rotate_button.setEnabled(not busy and bool(self._selected))
        self.remove_button.setEnabled(not busy and bool(self._selected))
        self.cancel_button.setVisible(busy)
        self.progress.setVisible(busy)
        if busy and self._operation_kind == "load":
            self.progress.setRange(0, 0)
            self.progress.setFormat(PDF_LOADING_PROGRESS)

    def _set_document_mode(self, enabled: bool) -> None:
        self.grid.set_document_mode(enabled)
        self._selection_changed([])
        self.rotate_button.setVisible(not enabled)
        self.remove_button.setVisible(not enabled)

    def _load_progress(self, loaded: int) -> None:
        self.progress.setFormat(f"{PDF_LOADING_PROGRESS} {loaded}")

    def _merge_progress(self, current: int, total: int) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(current)
        self.progress.setFormat(PDF_MERGE_PROGRESS + " %p %")

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, PDF_IMPORT_ERROR_TITLE, message)

    def _merge_succeeded(self, result: str) -> None:
        dialog = QMessageBox(self)
        dialog.setWindowTitle(PDF_SUCCESS_TITLE)
        dialog.setText(PDF_SUCCESS_MESSAGE.format(path=result))
        open_button = dialog.addButton(OPEN_FOLDER, QMessageBox.ButtonRole.ActionRole)
        dialog.addButton(CLOSE, QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        if dialog.clickedButton() is open_button:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(result).parent)))

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.viewmodel.shutdown()
        super().closeEvent(event)
