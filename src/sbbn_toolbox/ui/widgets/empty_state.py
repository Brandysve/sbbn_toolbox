"""État vide réutilisable."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from sbbn_toolbox.ui.theme.tokens import SPACING


class EmptyState(QFrame):
    """Explique le contenu attendu lorsqu'une collection est vide."""

    def __init__(self, title: str, description: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("emptyState")
        self.setMinimumHeight(145)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.xl, SPACING.xl, SPACING.xl, SPACING.xl)
        layout.setSpacing(SPACING.sm)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_label = QLabel(title)
        title_label.setProperty("role", "emptyTitle")
        layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignCenter)

        description_label = QLabel(description)
        description_label.setProperty("role", "emptyDescription")
        description_label.setWordWrap(True)
        description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(description_label)
