"""Notification légère et non bloquante."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from sbbn_toolbox.ui.theme.tokens import SPACING


class Toast(QFrame):
    """Bannière temporaire annoncée aussi aux technologies d'assistance."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setVisible(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING.lg, SPACING.md, SPACING.lg, SPACING.md)
        self._message = QLabel()
        self._message.setWordWrap(True)
        layout.addWidget(self._message)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, message: str, duration_ms: int = 3000) -> None:
        """Afficher un message pendant une durée limitée."""
        self._message.setText(message)
        self.setAccessibleName(message)
        self.setVisible(True)
        self.raise_()
        self._timer.start(duration_ms)
        self.setFocus(Qt.FocusReason.OtherFocusReason)
