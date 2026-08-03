"""Structure visuelle des paramètres."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from sbbn_toolbox.constants import (
    CHOOSE_FOLDER,
    DATA_PATH_LABEL,
    DATA_PATH_PLACEHOLDER,
    DATA_SECTION_DESCRIPTION,
    DATA_SECTION_TITLE,
    INTERFACE_SECTION_DESCRIPTION,
    INTERFACE_SECTION_TITLE,
    PHASE_PLACEHOLDER_MESSAGE,
    SCALE_LABEL,
    SCALE_VALUE,
    SETTINGS_DESCRIPTION,
    SETTINGS_TITLE,
)
from sbbn_toolbox.ui.theme.tokens import SPACING
from sbbn_toolbox.ui.widgets.buttons import ActionButton
from sbbn_toolbox.ui.widgets.page_header import PageHeader


class SettingsPage(QWidget):
    """Page factice : aucune préférence n'est persistée en Phase 1."""

    notification_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.xxxl, SPACING.xxl, SPACING.xxxl, SPACING.xxl)
        layout.setSpacing(SPACING.xl)

        layout.addWidget(PageHeader(SETTINGS_TITLE, SETTINGS_DESCRIPTION))
        layout.addWidget(self._data_card())
        layout.addWidget(self._interface_card())
        layout.addStretch()

    def _data_card(self) -> QFrame:
        card = QFrame()
        card.setProperty("card", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(SPACING.xl, SPACING.xl, SPACING.xl, SPACING.xl)
        layout.setSpacing(SPACING.md)

        title = QLabel(DATA_SECTION_TITLE)
        title.setProperty("role", "sectionTitle")
        layout.addWidget(title)
        description = QLabel(DATA_SECTION_DESCRIPTION)
        description.setProperty("role", "muted")
        description.setWordWrap(True)
        layout.addWidget(description)
        label = QLabel(DATA_PATH_LABEL)
        label.setProperty("role", "muted")
        layout.addWidget(label)

        row = QHBoxLayout()
        path = QLineEdit(DATA_PATH_PLACEHOLDER)
        path.setReadOnly(True)
        row.addWidget(path, stretch=1)
        choose_button = ActionButton(CHOOSE_FOLDER, variant="secondary")
        choose_button.clicked.connect(
            lambda: self.notification_requested.emit(PHASE_PLACEHOLDER_MESSAGE)
        )
        row.addWidget(choose_button)
        layout.addLayout(row)
        return card

    def _interface_card(self) -> QFrame:
        card = QFrame()
        card.setProperty("card", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(SPACING.xl, SPACING.xl, SPACING.xl, SPACING.xl)
        layout.setSpacing(SPACING.md)

        title = QLabel(INTERFACE_SECTION_TITLE)
        title.setProperty("role", "sectionTitle")
        layout.addWidget(title)
        description = QLabel(INTERFACE_SECTION_DESCRIPTION)
        description.setProperty("role", "muted")
        description.setWordWrap(True)
        layout.addWidget(description)
        scale = QLabel(f"{SCALE_LABEL}  ·  {SCALE_VALUE}")
        scale.setProperty("role", "muted")
        scale.setWordWrap(True)
        layout.addWidget(scale)
        return card
