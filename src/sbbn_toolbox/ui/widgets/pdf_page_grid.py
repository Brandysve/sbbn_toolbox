"""Grille globale de pages PDF avec sélection multiple et ordre déplaçable."""

from PySide6.QtCore import QModelIndex, Qt, QTimer, Signal
from PySide6.QtGui import QResizeEvent, QShowEvent
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem, QWidget

from sbbn_toolbox.domain.pdf_page_item import PdfPageItem
from sbbn_toolbox.ui.widgets.pdf_thumbnail_card import PdfThumbnailCard


class PdfPageGrid(QListWidget):
    """Vue uniquement : l'ordre métier reste dans le viewmodel."""

    order_changed = Signal(list)
    selection_changed = Signal(list)
    preview_requested = Signal(str, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pdfPageGrid")
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setWrapping(True)
        self.setGridSize(self.gridSize().expandedTo(self.minimumSizeHint()))
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSpacing(8)
        self._requested: set[str] = set()
        self.model().rowsMoved.connect(self._emit_order)
        self.itemSelectionChanged.connect(self._emit_selection)
        self.verticalScrollBar().valueChanged.connect(self.request_visible_previews)

    def set_pages(self, pages: list[PdfPageItem]) -> None:
        self.clear()
        self._requested.clear()
        for page in pages:
            self.append_page(page)
        self._schedule_visible_request()

    def append_page(self, page: PdfPageItem) -> None:
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, page.identifier)
        card = PdfThumbnailCard(page)
        item.setSizeHint(card.sizeHint())
        self.addItem(item)
        self.setItemWidget(item, card)
        self._schedule_visible_request()

    def update_page(self, page: PdfPageItem) -> None:
        for index in range(self.count()):
            item = self.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == page.identifier:
                card = PdfThumbnailCard(page)
                item.setSizeHint(card.sizeHint())
                self.setItemWidget(item, card)
                self._requested.discard(page.identifier)
                break
        self._schedule_visible_request()

    def set_thumbnail(self, identifier: str, payload: bytes) -> None:
        for index in range(self.count()):
            item = self.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == identifier:
                card = self.itemWidget(item)
                if isinstance(card, PdfThumbnailCard):
                    card.set_thumbnail(payload)
                return

    def identifiers(self) -> list[str]:
        return [
            str(self.item(index).data(Qt.ItemDataRole.UserRole)) for index in range(self.count())
        ]

    def selected_identifiers(self) -> list[str]:
        return [str(item.data(Qt.ItemDataRole.UserRole)) for item in self.selectedItems()]

    def request_visible_previews(self) -> None:
        if not self.isVisible() or not self.count():
            return
        visible_rows: list[int] = []
        viewport_rect = self.viewport().rect()
        for index in range(self.count()):
            if self.visualItemRect(self.item(index)).intersects(viewport_rect):
                visible_rows.append(index)
        for index in visible_rows:
            self._request(index, priority=1)
        if visible_rows:
            for index in range(visible_rows[-1] + 1, min(self.count(), visible_rows[-1] + 5)):
                self._request(index, priority=0)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._schedule_visible_request()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._schedule_visible_request()

    def _request(self, index: int, priority: int) -> None:
        identifier = str(self.item(index).data(Qt.ItemDataRole.UserRole))
        if identifier not in self._requested:
            self._requested.add(identifier)
            self.preview_requested.emit(identifier, priority)

    def _schedule_visible_request(self) -> None:
        QTimer.singleShot(0, self.request_visible_previews)

    def _emit_selection(self) -> None:
        self.selection_changed.emit(self.selected_identifiers())

    def _emit_order(
        self,
        parent: QModelIndex,
        start: int,
        end: int,
        destination: QModelIndex,
        row: int,
    ) -> None:
        del parent, start, end, destination, row
        self.order_changed.emit(self.identifiers())
