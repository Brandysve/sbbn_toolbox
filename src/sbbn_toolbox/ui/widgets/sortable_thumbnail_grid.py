"""Liste de vignettes réordonnable par glisser-déposer."""

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem, QWidget

from sbbn_toolbox.domain.image_item import ImageItem
from sbbn_toolbox.ui.widgets.thumbnail_card import ThumbnailCard


class SortableThumbnailGrid(QListWidget):
    """Présenter l'ordre final et émettre chaque réorganisation."""

    order_changed = Signal(list)
    rotate_requested = Signal(str)
    remove_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("imageThumbnailGrid")
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.model().rowsMoved.connect(self._emit_order)

    def set_items(self, images: list[ImageItem]) -> None:
        """Reconstruire les cartes à partir du modèle ordonné."""
        self.clear()
        for image in images:
            list_item = QListWidgetItem()
            list_item.setData(256, image.identifier)
            card = ThumbnailCard(image)
            card.rotate_requested.connect(self.rotate_requested)
            card.remove_requested.connect(self.remove_requested)
            list_item.setSizeHint(card.sizeHint())
            self.addItem(list_item)
            self.setItemWidget(list_item, card)

    def identifiers(self) -> list[str]:
        return [str(self.item(index).data(256)) for index in range(self.count())]

    def selected_identifiers(self) -> list[str]:
        return [str(item.data(256)) for item in self.selectedItems()]

    def remove_selected(self) -> None:
        for identifier in self.selected_identifiers():
            self.remove_requested.emit(identifier)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Delete:
            self.remove_selected()
            event.accept()
            return
        super().keyPressEvent(event)

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
