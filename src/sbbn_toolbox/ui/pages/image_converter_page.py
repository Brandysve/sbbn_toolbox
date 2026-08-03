"""Parcours complet Images vers PDF."""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QCloseEvent, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from sbbn_toolbox.constants import (
    ADD_IMAGES,
    CANCEL_CONVERSION,
    CLEAR_IMAGES,
    CLOSE,
    CONVERSION_CANCELLED,
    CONVERSION_PROGRESS,
    CONVERSION_SUCCESS_MESSAGE,
    CONVERSION_SUCCESS_TITLE,
    CREATE_PDF,
    IMAGE_FILES_FILTER,
    IMAGES_DESCRIPTION,
    IMAGES_DROP_DESCRIPTION,
    IMAGES_DROP_TITLE,
    IMAGES_EMPTY_DESCRIPTION,
    IMAGES_EMPTY_TITLE,
    IMAGES_TITLE,
    IMPORT_ERROR_TITLE,
    MARGINS_LABEL,
    OPEN_FOLDER,
    ORIENTATION_AUTO,
    ORIENTATION_LABEL,
    ORIENTATION_LANDSCAPE,
    ORIENTATION_PORTRAIT,
    OUTPUT_OPTIONS_TITLE,
    OVERWRITE_MESSAGE,
    OVERWRITE_TITLE,
    PAGE_SIZE_A4,
    PAGE_SIZE_LABEL,
    PAGE_SIZE_ORIGINAL,
    PDF_FILES_FILTER,
    SAVE_PDF_TITLE,
    SHORTCUT_ADD_TOOLTIP,
    SHORTCUT_CANCEL_TOOLTIP,
    SHORTCUT_REMOVE_TOOLTIP,
    SHORTCUT_SAVE_TOOLTIP,
    SHORTCUT_SELECT_ALL_TOOLTIP,
)
from sbbn_toolbox.domain.image_item import ImageItem
from sbbn_toolbox.services.image_to_pdf_service import (
    ImagePdfOptions,
    PageMode,
    PageOrientation,
)
from sbbn_toolbox.ui.theme.tokens import SPACING
from sbbn_toolbox.ui.widgets.buttons import ActionButton
from sbbn_toolbox.ui.widgets.drop_zone import DropZone
from sbbn_toolbox.ui.widgets.empty_state import EmptyState
from sbbn_toolbox.ui.widgets.page_header import PageHeader
from sbbn_toolbox.ui.widgets.sortable_thumbnail_grid import SortableThumbnailGrid
from sbbn_toolbox.viewmodels.image_converter_vm import ImageConverterViewModel


class ImageConverterPage(QWidget):
    """Importer, ordonner et convertir des images sans toucher aux sources."""

    notification_requested = Signal(str)

    def __init__(
        self,
        viewmodel: ImageConverterViewModel | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.viewmodel = viewmodel or ImageConverterViewModel()
        self._last_result: Path | None = None
        self._exported_signature: tuple[tuple[str, int], ...] | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.xxxl, SPACING.xxl, SPACING.xxxl, SPACING.xxl)
        layout.setSpacing(SPACING.xl)

        layout.addWidget(PageHeader(IMAGES_TITLE, IMAGES_DESCRIPTION))

        self.drop_zone = DropZone(IMAGES_DROP_TITLE, IMAGES_DROP_DESCRIPTION, ADD_IMAGES)
        self.drop_zone.selection_requested.connect(self._choose_images)
        self.drop_zone.setToolTip(SHORTCUT_ADD_TOOLTIP)
        self.drop_zone.files_dropped.connect(self._import_dropped_files)
        layout.addWidget(self.drop_zone)
        self.empty_state = EmptyState(IMAGES_EMPTY_TITLE, IMAGES_EMPTY_DESCRIPTION)
        layout.addWidget(self.empty_state)
        self.grid = SortableThumbnailGrid()
        self.grid.setMinimumHeight(230)
        self.grid.order_changed.connect(self.viewmodel.reorder)
        self.grid.rotate_requested.connect(self.viewmodel.rotate)
        self.grid.remove_requested.connect(self.viewmodel.remove)
        self.grid.hide()
        layout.addWidget(self.grid, stretch=1)

        layout.addWidget(self._options_panel())

        actions = QHBoxLayout()
        self.clear_button = ActionButton(CLEAR_IMAGES, variant="secondary")
        self.clear_button.setEnabled(False)
        self.clear_button.clicked.connect(self.viewmodel.clear)
        actions.addWidget(self.clear_button)
        actions.addStretch()
        self.cancel_button = ActionButton(CANCEL_CONVERSION, variant="secondary")
        self.cancel_button.setObjectName("cancelConversionButton")
        self.cancel_button.clicked.connect(self.viewmodel.cancel)
        self.cancel_button.setToolTip(SHORTCUT_CANCEL_TOOLTIP)
        self.cancel_button.hide()
        actions.addWidget(self.cancel_button)
        self.create_button = ActionButton(CREATE_PDF)
        self.create_button.setEnabled(False)
        self.create_button.setToolTip(IMAGES_EMPTY_TITLE)
        self.create_button.clicked.connect(self._choose_destination)
        actions.addWidget(self.create_button)
        layout.addLayout(actions)

        self.progress = QProgressBar()
        self.progress.setFormat(CONVERSION_PROGRESS + " %p %")
        self.progress.hide()
        layout.addWidget(self.progress)

        self.viewmodel.items_changed.connect(self._update_items)
        self.viewmodel.import_failed.connect(self._show_import_error)
        self.viewmodel.progress_changed.connect(self._update_progress)
        self.viewmodel.busy_changed.connect(self._set_busy)
        self.viewmodel.conversion_succeeded.connect(self._conversion_succeeded)
        self.viewmodel.conversion_failed.connect(self._show_import_error)
        self.viewmodel.conversion_cancelled.connect(
            lambda: self.notification_requested.emit(CONVERSION_CANCELLED)
        )
        self._create_shortcuts()

    @property
    def has_unexported_selection(self) -> bool:
        return (
            bool(self.viewmodel.items) and self._selection_signature() != self._exported_signature
        )

    def _create_shortcuts(self) -> None:
        self._shortcut(QKeySequence.StandardKey.Open, self._choose_images)
        self._shortcut(QKeySequence(Qt.Key.Key_Delete), self.grid.remove_selected)
        self._shortcut(QKeySequence.StandardKey.SelectAll, self.grid.selectAll)
        self._shortcut(QKeySequence.StandardKey.Save, self._save_if_available)
        self._shortcut(QKeySequence(Qt.Key.Key_Escape), self._cancel_if_busy)
        self.create_button.setToolTip(SHORTCUT_SAVE_TOOLTIP)
        self.grid.setToolTip(f"{SHORTCUT_SELECT_ALL_TOOLTIP} · {SHORTCUT_REMOVE_TOOLTIP}")

    def _shortcut(self, key: QKeySequence | QKeySequence.StandardKey, callback: object) -> None:
        shortcut = QShortcut(key, self)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(callback)

    def _save_if_available(self) -> None:
        if self.create_button.isEnabled():
            self._choose_destination()

    def _cancel_if_busy(self) -> None:
        if self.viewmodel.is_busy:
            self.viewmodel.cancel()

    def _selection_signature(self) -> tuple[tuple[str, int], ...]:
        return tuple((item.identifier, item.rotation) for item in self.viewmodel.items)

    def _options_panel(self) -> QFrame:
        panel = QFrame()
        panel.setProperty("card", True)
        form = QFormLayout(panel)
        form.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        form.setSpacing(SPACING.md)
        title = QLabel(OUTPUT_OPTIONS_TITLE)
        title.setProperty("role", "sectionTitle")
        form.addRow(title)
        self.page_size = QComboBox()
        self.page_size.addItem(PAGE_SIZE_ORIGINAL, PageMode.ORIGINAL)
        self.page_size.addItem(PAGE_SIZE_A4, PageMode.A4)
        form.addRow(PAGE_SIZE_LABEL, self.page_size)
        self.orientation = QComboBox()
        self.orientation.addItem(ORIENTATION_AUTO, PageOrientation.AUTO)
        self.orientation.addItem(ORIENTATION_PORTRAIT, PageOrientation.PORTRAIT)
        self.orientation.addItem(ORIENTATION_LANDSCAPE, PageOrientation.LANDSCAPE)
        self.orientation.setEnabled(False)
        self.page_size.currentIndexChanged.connect(
            lambda: self.orientation.setEnabled(self.page_size.currentData() is PageMode.A4)
        )
        form.addRow(ORIENTATION_LABEL, self.orientation)
        self.margins = QSpinBox()
        self.margins.setRange(0, 50)
        self.margins.setSuffix(" mm")
        form.addRow(MARGINS_LABEL, self.margins)
        return panel

    def _choose_images(self) -> None:
        filenames, _ = QFileDialog.getOpenFileNames(self, ADD_IMAGES, "", IMAGE_FILES_FILTER)
        self.viewmodel.import_files([Path(filename) for filename in filenames])

    def _import_dropped_files(self, filenames: list[str]) -> None:
        self.viewmodel.import_files([Path(filename) for filename in filenames])

    def _choose_destination(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(self, SAVE_PDF_TITLE, "", PDF_FILES_FILTER)
        if not filename:
            return
        destination = Path(filename)
        if destination.suffix.lower() != ".pdf":
            destination = destination.with_suffix(".pdf")
        overwrite = False
        if destination.exists():
            answer = QMessageBox.question(
                self,
                OVERWRITE_TITLE,
                OVERWRITE_MESSAGE,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer is not QMessageBox.StandardButton.Yes:
                return
            overwrite = True
        options = ImagePdfOptions(
            page_mode=self.page_size.currentData(),
            orientation=self.orientation.currentData(),
            margin_mm=float(self.margins.value()),
        )
        self.viewmodel.start_conversion(destination, options, overwrite=overwrite)

    def _update_items(self, items: list[ImageItem]) -> None:
        has_items = bool(items)
        self.grid.set_items(items)
        self.grid.setVisible(has_items)
        self.empty_state.setVisible(not has_items)
        self.create_button.setEnabled(has_items and not self.viewmodel.is_busy)
        self.clear_button.setEnabled(has_items and not self.viewmodel.is_busy)

    def _set_busy(self, busy: bool) -> None:
        self.drop_zone.setEnabled(not busy)
        self.grid.setEnabled(not busy)
        self.page_size.setEnabled(not busy)
        self.orientation.setEnabled(not busy and self.page_size.currentData() is PageMode.A4)
        self.margins.setEnabled(not busy)
        self.clear_button.setEnabled(not busy and bool(self.viewmodel.items))
        self.create_button.setEnabled(not busy and bool(self.viewmodel.items))
        self.cancel_button.setVisible(busy)
        self.progress.setVisible(busy)
        if busy:
            self.progress.setValue(0)

    def _update_progress(self, current: int, total: int) -> None:
        self.progress.setMaximum(total)
        self.progress.setValue(current)

    def _show_import_error(self, message: str) -> None:
        QMessageBox.warning(self, IMPORT_ERROR_TITLE, message)

    def _conversion_succeeded(self, result: str) -> None:
        self._last_result = Path(result)
        self._exported_signature = self._selection_signature()
        dialog = QMessageBox(self)
        dialog.setWindowTitle(CONVERSION_SUCCESS_TITLE)
        dialog.setText(CONVERSION_SUCCESS_MESSAGE.format(path=result))
        open_button = dialog.addButton(OPEN_FOLDER, QMessageBox.ButtonRole.ActionRole)
        dialog.addButton(CLOSE, QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        if dialog.clickedButton() is open_button:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(result).parent)))

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.viewmodel.shutdown()
        super().closeEvent(event)
