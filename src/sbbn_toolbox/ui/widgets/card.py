"""Cartes réutilisables de l'interface."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from sbbn_toolbox.constants import OPEN_TOOL
from sbbn_toolbox.ui.theme.tokens import SPACING
from sbbn_toolbox.ui.widgets.buttons import ActionButton


class FeatureCard(QFrame):
    """Carte présentant une fonctionnalité depuis l'accueil."""

    activated = Signal()

    def __init__(
        self,
        marker: str,
        title: str,
        description: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("card", True)
        self.setMinimumWidth(270)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.xl, SPACING.xl, SPACING.xl, SPACING.xl)
        layout.setSpacing(SPACING.lg)

        marker_row = QHBoxLayout()
        marker_label = QLabel(marker)
        marker_label.setProperty("role", "cardIcon")
        marker_label.setFixedSize(46, 46)
        marker_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        marker_row.addWidget(marker_label)
        marker_row.addStretch()
        layout.addLayout(marker_row)

        title_label = QLabel(title)
        title_label.setProperty("role", "cardTitle")
        layout.addWidget(title_label)

        description_label = QLabel(description)
        description_label.setProperty("role", "description")
        description_label.setWordWrap(True)
        layout.addWidget(description_label)
        layout.addStretch()

        button = ActionButton(OPEN_TOOL, variant="secondary")
        button.clicked.connect(self.activated)
        layout.addWidget(button)
