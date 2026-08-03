"""Grille globale de pages PDF avec sélection multiple et ordre déplaçable."""

from pathlib import Path

from PySide6.QtCore import QModelIndex, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QDrag,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QResizeEvent,
    QShowEvent,
)
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem, QWidget

from sbbn_toolbox.domain.pdf_page_item import PdfPageItem
from sbbn_toolbox.ui.theme.tokens import COLORS, SPACING
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
        self.setMovement(QListWidget.Movement.Snap)
        self.setWrapping(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        # Le repère natif varie selon la plateforme et peut rester peint sous Linux.
        self.setDropIndicatorShown(False)
        self.setDragDropOverwriteMode(False)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSpacing(8)
        self._requested: set[str] = set()
        self._all_pages: list[PdfPageItem] = []
        self._pages_by_id: dict[str, PdfPageItem] = {}
        self._display_pages_by_id: dict[str, PdfPageItem] = {}
        self._document_mode = False
        self._drop_indicator: QRect | None = None
        self.model().rowsMoved.connect(self._emit_order)
        self.itemSelectionChanged.connect(self._emit_selection)
        self.verticalScrollBar().valueChanged.connect(self.request_visible_previews)

    def set_pages(self, pages: list[PdfPageItem]) -> None:
        self._all_pages = list(pages)
        self.clear()
        self._requested.clear()
        self._pages_by_id = {page.identifier: page for page in pages}
        self._display_pages_by_id.clear()
        if self._document_mode:
            for source_path in self._ordered_sources(pages):
                source_pages = sorted(
                    (page for page in pages if page.source_path == source_path),
                    key=lambda page: page.source_page_index,
                )
                representative = source_pages[0]
                self._append_display_item(
                    str(source_path),
                    representative,
                    page_count=len(source_pages),
                )
        else:
            for page in pages:
                self._append_display_item(page.identifier, page)
        self._schedule_visible_request()

    def append_page(self, page: PdfPageItem) -> None:
        self._all_pages.append(page)
        self._pages_by_id[page.identifier] = page
        if not self._document_mode:
            self._append_display_item(page.identifier, page)
            return
        document_identifier = str(page.source_path)
        if document_identifier not in self._display_pages_by_id:
            self._append_display_item(document_identifier, page, page_count=1)
            return
        for index in range(self.count()):
            item = self.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == document_identifier:
                card = self.itemWidget(item)
                if isinstance(card, PdfThumbnailCard):
                    page_count = sum(
                        current.source_path == page.source_path for current in self._all_pages
                    )
                    card.set_page_count(page_count)
                    item.setSizeHint(card.sizeHint())
                return

    def _append_display_item(
        self,
        display_identifier: str,
        page: PdfPageItem,
        *,
        page_count: int | None = None,
    ) -> None:
        self._display_pages_by_id[display_identifier] = page
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, display_identifier)
        item.setData(Qt.ItemDataRole.UserRole + 1, page.identifier)
        card = PdfThumbnailCard(page, page_count=page_count)
        item.setSizeHint(card.sizeHint())
        self.addItem(item)
        self.setItemWidget(item, card)
        if self.count() == 1:
            self._request(0, priority=2)
        self._schedule_visible_request()

    def update_page(self, page: PdfPageItem) -> None:
        pages = [
            page if current.identifier == page.identifier else current
            for current in self._all_pages
        ]
        self.set_pages(pages)

    def set_thumbnail(self, identifier: str, payload: bytes) -> None:
        for index in range(self.count()):
            item = self.item(index)
            if item.data(Qt.ItemDataRole.UserRole + 1) == identifier:
                card = self.itemWidget(item)
                if isinstance(card, PdfThumbnailCard):
                    card.set_thumbnail(payload)
                return

    @property
    def document_mode(self) -> bool:
        return self._document_mode

    def set_document_mode(self, enabled: bool) -> None:
        if enabled == self._document_mode:
            return
        self._document_mode = enabled
        pages = self._pages_in_document_order() if enabled else list(self._all_pages)
        self.set_pages(pages)
        self.order_changed.emit([page.identifier for page in pages])

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

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.source() is self:
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            event.ignore()

    def startDrag(self, supported_actions: Qt.DropAction) -> None:  # noqa: N802
        """Lancer un drag sans pixmap ni suppression automatique par QListWidget."""
        del supported_actions
        indexes = self.selectedIndexes()
        if not indexes:
            return
        mime_data = self.model().mimeData(indexes)
        if mime_data is None:
            return
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        try:
            drag.exec(Qt.DropAction.MoveAction)
        finally:
            self._finish_drag_visuals()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        if event.source() is not self:
            event.ignore()
            return
        self._update_drop_indicator(event.position().toPoint())
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802
        self._clear_drop_indicator()
        event.accept()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._drop_indicator is None:
            return
        painter = QPainter(self.viewport())
        painter.setPen(
            QPen(
                QColor(COLORS.primary),
                SPACING.xs,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        painter.drawLine(
            self._drop_indicator.topLeft(),
            self._drop_indicator.bottomLeft(),
        )
        painter.end()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        """Appliquer un ordre déterministe, indépendamment du style Qt de la plateforme."""
        if event.source() is not self:
            self._finish_drag_visuals()
            event.ignore()
            return
        dragged = self.selected_identifiers()
        if not dragged:
            self._finish_drag_visuals()
            event.accept()
            return
        position = event.position().toPoint()
        target_identifier, insert_after = self._drop_location(position)
        # Attendre la fin de la boucle native QDrag avant de reconstruire les widgets.
        # Sous Linux, une reconstruction immédiate laisse parfois le pixmap du drag peint.
        QTimer.singleShot(
            0,
            lambda: self._complete_drop(dragged, target_identifier, insert_after),
        )
        self._clear_drop_indicator()
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        super().mouseReleaseEvent(event)
        self._clear_drop_indicator()

    def _apply_drop_order(
        self,
        dragged: list[str],
        target_identifier: str | None,
        insert_after: bool,
    ) -> bool:
        """Réordonner la vue et émettre l'ordre métier après un dépôt."""
        current = self.identifiers()
        dragged_set = set(dragged)
        if not dragged_set or not dragged_set.issubset(current):
            return False
        remaining = [identifier for identifier in current if identifier not in dragged_set]
        moving = [identifier for identifier in current if identifier in dragged_set]
        if target_identifier is None:
            insertion = len(remaining)
        elif target_identifier in dragged_set:
            return False
        else:
            insertion = remaining.index(target_identifier) + int(insert_after)
        reordered = remaining[:insertion] + moving + remaining[insertion:]
        if reordered == current:
            return False
        if self._document_mode:
            pages = self._pages_for_document_keys(reordered)
        else:
            pages = [self._pages_by_id[identifier] for identifier in reordered]
        self.set_pages(pages)
        self.clearSelection()
        self.setCurrentRow(-1)
        self.order_changed.emit([page.identifier for page in pages])
        return True

    def _ordered_sources(self, pages: list[PdfPageItem]) -> list[Path]:
        return list(dict.fromkeys(page.source_path for page in pages))

    def _pages_in_document_order(self) -> list[PdfPageItem]:
        return self._pages_for_document_keys(
            [str(source_path) for source_path in self._ordered_sources(self._all_pages)]
        )

    def _pages_for_document_keys(self, keys: list[str]) -> list[PdfPageItem]:
        by_source: dict[str, list[PdfPageItem]] = {}
        for page in self._all_pages:
            by_source.setdefault(str(page.source_path), []).append(page)
        return [
            page
            for key in keys
            for page in sorted(by_source[key], key=lambda item: item.source_page_index)
        ]

    def _complete_drop(
        self,
        dragged: list[str],
        target_identifier: str | None,
        insert_after: bool,
    ) -> None:
        """Reconstruire la grille une fois le pixmap natif du drag libéré."""
        self._apply_drop_order(dragged, target_identifier, insert_after)
        self._finish_drag_visuals()

    def _drop_location(self, position: QPoint) -> tuple[str | None, bool]:
        target_item = self.itemAt(position)
        if target_item is None:
            return None, True
        target_rect = self.visualItemRect(target_item)
        if abs(position.y() - target_rect.center().y()) < target_rect.height() // 2:
            insert_after = position.x() > target_rect.center().x()
        else:
            insert_after = position.y() > target_rect.center().y()
        return str(target_item.data(Qt.ItemDataRole.UserRole)), insert_after

    def _update_drop_indicator(self, position: QPoint) -> None:
        target_item = self.itemAt(position)
        if target_item is None:
            if not self.count():
                self._clear_drop_indicator()
                return
            target_item = self.item(self.count() - 1)
            insert_after = True
        else:
            _, insert_after = self._drop_location(position)
        target_rect = self.visualItemRect(target_item)
        x = target_rect.right() + SPACING.sm if insert_after else target_rect.left() - SPACING.sm
        x = max(1, min(x, self.viewport().width() - SPACING.xs - 1))
        indicator = QRect(x, target_rect.top(), SPACING.xs, target_rect.height())
        if indicator != self._drop_indicator:
            previous = self._drop_indicator
            self._drop_indicator = indicator
            if previous is not None:
                self.viewport().update(previous.adjusted(-SPACING.sm, 0, SPACING.sm, 0))
            self.viewport().update(indicator.adjusted(-SPACING.sm, 0, SPACING.sm, 0))

    def _clear_drop_indicator(self) -> None:
        if self._drop_indicator is not None:
            previous = self._drop_indicator
            self._drop_indicator = None
            self.viewport().update(previous.adjusted(-SPACING.sm, 0, SPACING.sm, 0))

    def _finish_drag_visuals(self) -> None:
        self._clear_drop_indicator()
        self.clearSelection()
        self.setCurrentRow(-1)
        self.viewport().update()
        QTimer.singleShot(0, self._repaint_after_drag)

    def _repaint_after_drag(self) -> None:
        self.viewport().repaint()

    def _request(self, index: int, priority: int) -> None:
        identifier = str(self.item(index).data(Qt.ItemDataRole.UserRole + 1))
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
        if self._document_mode:
            pages = self._pages_for_document_keys(self.identifiers())
            self.order_changed.emit([page.identifier for page in pages])
        else:
            self.order_changed.emit(self.identifiers())
