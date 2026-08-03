"""En-tête commun aux pages."""

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from sbbn_toolbox.ui.theme.tokens import SPACING


class PageHeader(QWidget):
    """Titre et description d'une page."""

    def __init__(self, title: str, description: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING.sm)

        title_label = QLabel(title)
        title_label.setProperty("role", "pageTitle")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        description_label = QLabel(description)
        description_label.setProperty("role", "description")
        description_label.setWordWrap(True)
        layout.addWidget(description_label)
