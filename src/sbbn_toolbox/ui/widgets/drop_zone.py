"""Zone de dépôt visuelle, sans chargement de fichier en Phase 1."""

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from sbbn_toolbox.ui.theme.tokens import SPACING
from sbbn_toolbox.ui.widgets.buttons import ActionButton


class DropZone(QFrame):
    """Surface accessible réagissant au clic, au clavier et au glisser-déposer."""

    selection_requested = Signal()
    drop_detected = Signal()
    files_dropped = Signal(list)

    def __init__(
        self,
        title: str,
        description: str,
        button_text: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(title)
        self.setMinimumHeight(190)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.xl, SPACING.xl, SPACING.xl, SPACING.xl)
        layout.setSpacing(SPACING.sm)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        marker = QLabel("+")
        marker.setProperty("role", "cardIcon")
        marker.setAlignment(Qt.AlignmentFlag.AlignCenter)
        marker.setFixedSize(44, 44)
        layout.addWidget(marker, alignment=Qt.AlignmentFlag.AlignCenter)

        title_label = QLabel(title)
        title_label.setProperty("role", "dropTitle")
        layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignCenter)

        description_label = QLabel(description)
        description_label.setProperty("role", "muted")
        description_label.setWordWrap(True)
        description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(description_label)

        button = ActionButton(button_text, variant="secondary")
        button.clicked.connect(self.selection_requested)
        layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignCenter)

    def _set_drag_active(self, active: bool) -> None:
        self.setProperty("dragActive", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_drag_active(True)
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802
        self._set_drag_active(False)
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self._set_drag_active(False)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.drop_detected.emit()
            self.files_dropped.emit(
                [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
            )
        else:
            event.ignore()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.selection_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def event(self, event: QEvent) -> bool:
        return super().event(event)
